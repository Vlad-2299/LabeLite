"""Canvas widget — drawing, selection, move and resize of bounding boxes."""
import copy

from PyQt5.QtWidgets import QWidget, QMenu, QApplication
from PyQt5.QtCore import (Qt, QPointF, QRectF, pyqtSignal, QSize)
from PyQt5.QtGui import (QPainter, QPen, QBrush, QColor, QCursor, QPixmap,
                         QFont)

from libs.shape import Shape, HANDLE_SIZE

# ── cursor shapes for each of the 8 handles (TL TC TR RC BR BC BL LC) ──────
HANDLE_CURSORS = [
    Qt.SizeFDiagCursor,   # 0 TL
    Qt.SizeVerCursor,     # 1 TC
    Qt.SizeBDiagCursor,   # 2 TR
    Qt.SizeHorCursor,     # 3 RC
    Qt.SizeFDiagCursor,   # 4 BR
    Qt.SizeVerCursor,     # 5 BC
    Qt.SizeBDiagCursor,   # 6 BL
    Qt.SizeHorCursor,     # 7 LC
]

CURSOR_DEFAULT  = Qt.ArrowCursor
CURSOR_POINT    = Qt.PointingHandCursor
CURSOR_DRAW     = Qt.CrossCursor
CURSOR_MOVE     = Qt.SizeAllCursor

MIN_SIZE = 5   # Minimum box side length (image pixels)


class Canvas(QWidget):
    # ── signals ──────────────────────────────────────────────────────────────
    zoomRequest      = pyqtSignal(int)
    scrollRequest    = pyqtSignal(int, int)
    newShape         = pyqtSignal()
    # Emits (shape, old_points, new_points) after a move or resize finishes
    shapeMoved       = pyqtSignal(object, object, object)
    selectionChanged = pyqtSignal(bool)
    drawingPolygon   = pyqtSignal(bool)

    CREATING = 0
    EDITING  = 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode           = self.EDITING
        self.shapes          = []        # finalised shapes
        self.current         = None      # shape currently being drawn
        self.selected_shape  = None
        self.pixmap          = None
        self.scale           = 1.0
        self.label_font_size = 12
        self.verified        = False
        self._draw_square    = False
        self._drawing_color  = QColor(0, 120, 255)

        # context menus: [0] = regular, [1] = "copy/move here"
        self.menus = [QMenu(), QMenu()]

        # drag / resize state
        self._active_handle      = -1      # handle index during resize (-1 = none)
        self._drag_start_points  = None    # copy of shape.points at drag start
        self._prev_pos           = None    # last mouse pos in image coords (move)
        self._is_moving          = False
        self._is_resizing        = False

        # right-click "move/copy here" target
        self._move_target = None

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)

    # ── mode helpers ─────────────────────────────────────────────────────────
    def editing(self):
        return self._mode == self.EDITING

    def set_editing(self, value=True):
        self._mode = self.EDITING if value else self.CREATING
        if value:
            self.restore_cursor()
        else:
            self.setCursor(CURSOR_DRAW)
        self.drawingPolygon.emit(not value)

    def set_drawing_shape_to_square(self, flag):
        self._draw_square = flag

    def set_drawing_color(self, color):
        self._drawing_color = color

    def restore_cursor(self):
        self.setCursor(CURSOR_DEFAULT)

    # ── shape management ─────────────────────────────────────────────────────
    def load_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.shapes = []
        self.current = None
        self.selected_shape = None
        self.update()

    def load_shapes(self, shapes):
        self.shapes = list(shapes)
        self.current = None
        self.repaint()

    def reset_state(self):
        self.shapes = []
        self.current = None
        self.selected_shape = None
        self.pixmap = None
        self.verified = False
        self.update()

    def reset_all_lines(self):
        """Discard the shape awaiting labelling (called on label-dialog cancel)."""
        if self.shapes:
            self.shapes.pop()
        self.current = None
        self.set_editing(True)
        self.update()

    def set_last_label(self, text, line_color, fill_color):
        """Apply label + colours to the most recently created shape."""
        assert self.shapes, "No shapes to label"
        shape = self.shapes[-1]
        shape.label      = text
        shape.line_color = line_color
        shape.fill_color = fill_color
        return shape

    def select_shape(self, shape):
        self.selected_shape = shape
        self.update()

    def delete_selected(self):
        if self.selected_shape and self.selected_shape in self.shapes:
            shape = self.selected_shape
            self.shapes.remove(shape)
            self.selected_shape = None
            self.update()
            return shape
        return None

    def copy_selected_shape(self):
        if self.selected_shape:
            new_shape = copy.copy(self.selected_shape)
            offset    = QPointF(10, 10)
            new_shape.points = [p + offset for p in new_shape.points]
            self.shapes.append(new_shape)
            self.selected_shape = new_shape
            self.update()
            return new_shape
        return None

    def set_shape_visible(self, shape, value):
        shape.visible = value
        self.update()

    def snap_point_to_canvas(self, x, y):
        """Clamp (x, y) to image bounds.  Returns (x, y, was_snapped)."""
        if self.pixmap is None:
            return x, y, False
        w, h  = self.pixmap.width(), self.pixmap.height()
        sx    = max(0.0, min(float(x), float(w)))
        sy    = max(0.0, min(float(y), float(h)))
        snapped = (sx != x or sy != y)
        return sx, sy, snapped

    def end_move(self, copy=False):
        """Finalise a right-click 'copy/move here' operation."""
        if self.selected_shape and self._move_target:
            old_center = self.selected_shape.bounding_rect().center()
            offset     = self._move_target - old_center
            if copy:
                new_shape = copy_copy(self.selected_shape)
                new_shape.points = [p + offset for p in new_shape.points]
                self.shapes.append(new_shape)
                self.selected_shape = new_shape
            else:
                old_pts = [QPointF(p) for p in self.selected_shape.points]
                self.selected_shape.points = [p + offset for p in self.selected_shape.points]
                new_pts = [QPointF(p) for p in self.selected_shape.points]
                self.shapeMoved.emit(self.selected_shape, old_pts, new_pts)
            self._move_target = None
            self.update()

    # ── coordinate transform ─────────────────────────────────────────────────
    def _to_img(self, widget_point):
        """Map widget QPoint/QPointF → image QPointF."""
        return QPointF(widget_point.x() / self.scale,
                       widget_point.y() / self.scale)

    def _clamp_to_image(self, pt):
        if self.pixmap is None:
            return pt
        x = max(0.0, min(pt.x(), float(self.pixmap.width())))
        y = max(0.0, min(pt.y(), float(self.pixmap.height())))
        return QPointF(x, y)

    # ── handle detection ─────────────────────────────────────────────────────
    def _get_handle_at(self, img_pos):
        if self.selected_shape is None:
            return -1
        threshold = HANDLE_SIZE / (self.scale)   # pixels in image space
        for i, h in enumerate(self.selected_shape.get_handles()):
            if (img_pos - h).manhattanLength() <= threshold:
                return i
        return -1

    def _get_shape_at(self, img_pos):
        # Check in reverse order so top-most shapes are picked first
        for shape in reversed(self.shapes):
            if shape.visible and shape.contains_point(img_pos):
                return shape
        return None

    # ── apply resize ─────────────────────────────────────────────────────────
    def _apply_handle_drag(self, img_pos):
        shape = self.selected_shape
        if shape is None:
            return
        r = shape.bounding_rect()
        h = self._active_handle

        # Move the appropriate edge(s)
        if   h == 0: r.setTopLeft(img_pos)
        elif h == 1: r.setTop(img_pos.y())
        elif h == 2: r.setTopRight(img_pos)
        elif h == 3: r.setRight(img_pos.x())
        elif h == 4: r.setBottomRight(img_pos)
        elif h == 5: r.setBottom(img_pos.y())
        elif h == 6: r.setBottomLeft(img_pos)
        elif h == 7: r.setLeft(img_pos.x())

        r = r.normalized()
        if r.width() < MIN_SIZE:
            r.setWidth(MIN_SIZE)
        if r.height() < MIN_SIZE:
            r.setHeight(MIN_SIZE)
        shape.points = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
        self.update()

    # ── mouse events ─────────────────────────────────────────────────────────
    def mousePressEvent(self, ev):
        pos = self._clamp_to_image(self._to_img(ev.pos()))

        if ev.button() == Qt.LeftButton:
            if self._mode == self.CREATING:
                # Start drawing a new box
                self.current = Shape()
                self.current.line_color = self._drawing_color
                self.current.fill_color = self._drawing_color
                self.current.add_point(pos)
                self.current.add_point(pos)   # second point tracks mouse
                self.update()

            elif self._mode == self.EDITING:
                # Check if on a resize handle of the selected shape
                handle = self._get_handle_at(pos)
                if handle >= 0:
                    self._active_handle     = handle
                    self._drag_start_points = [QPointF(p) for p in self.selected_shape.points]
                    self._is_resizing       = True
                    return

                # Check if on any shape
                shape = self._get_shape_at(pos)
                prev  = self.selected_shape
                self.selected_shape = shape
                if shape:
                    self._drag_start_points = [QPointF(p) for p in shape.points]
                    self._prev_pos          = pos
                    self._is_moving         = True
                    self.setCursor(CURSOR_MOVE)
                else:
                    self.restore_cursor()

                if shape != prev:
                    self.selectionChanged.emit(shape is not None)
                self.update()

        elif ev.button() == Qt.RightButton and self._mode == self.EDITING:
            # Right-click on a shape → select it and show the shape context menu
            shape = self._get_shape_at(pos)
            if shape:
                prev = self.selected_shape
                self.selected_shape = shape
                if shape != prev:
                    self.selectionChanged.emit(True)
                self.update()
                self.menus[1].exec_(ev.globalPos())

    def mouseMoveEvent(self, ev):
        pos = self._clamp_to_image(self._to_img(ev.pos()))

        if self._mode == self.CREATING and self.current:
            if self._draw_square:
                dx = pos.x() - self.current.points[0].x()
                dy = pos.y() - self.current.points[0].y()
                side = min(abs(dx), abs(dy))
                pos  = QPointF(
                    self.current.points[0].x() + (side if dx >= 0 else -side),
                    self.current.points[0].y() + (side if dy >= 0 else -side),
                )
            self.current.points[1] = pos
            self.update()
            return

        if self._mode == self.EDITING:
            if self._is_resizing and self.selected_shape:
                self._apply_handle_drag(pos)
                return

            if self._is_moving and self.selected_shape and self._prev_pos:
                delta = pos - self._prev_pos
                self.selected_shape.points = [p + delta for p in self.selected_shape.points]
                self._prev_pos = pos
                self.update()
                return

            # Hover: update cursor
            handle = self._get_handle_at(pos)
            if handle >= 0:
                self.setCursor(HANDLE_CURSORS[handle])
            elif self._get_shape_at(pos):
                self.setCursor(CURSOR_POINT)
            else:
                self.restore_cursor()

    def mouseReleaseEvent(self, ev):
        pos = self._clamp_to_image(self._to_img(ev.pos()))

        if ev.button() == Qt.LeftButton:
            if self._mode == self.CREATING and self.current:
                # Normalise the two corner points into 4 corners
                p0 = self.current.points[0]
                p1 = self.current.points[1]
                r  = QRectF(p0, p1).normalized()
                if r.width() >= MIN_SIZE and r.height() >= MIN_SIZE:
                    self.current.points = [
                        r.topLeft(), r.topRight(),
                        r.bottomRight(), r.bottomLeft(),
                    ]
                    self.current.close()
                    self.shapes.append(self.current)
                    self.current = None
                    self.newShape.emit()
                else:
                    self.current = None
                self.update()

            elif self._mode == self.EDITING:
                if (self._is_resizing or self._is_moving) and self.selected_shape:
                    new_pts  = [QPointF(p) for p in self.selected_shape.points]
                    old_pts  = self._drag_start_points or new_pts
                    # Only emit if something actually changed
                    moved = any(
                        abs(o.x() - n.x()) > 0.5 or abs(o.y() - n.y()) > 0.5
                        for o, n in zip(old_pts, new_pts)
                    )
                    if moved:
                        self.shapeMoved.emit(self.selected_shape, old_pts, new_pts)

                self._is_moving    = False
                self._is_resizing  = False
                self._active_handle = -1
                self._drag_start_points = None
                self._prev_pos     = None
                self.restore_cursor()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape and self._mode == self.CREATING:
            self.current = None
            self.set_editing(True)
            self.update()
        else:
            super().keyPressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if self._mode == self.EDITING and self.selected_shape:
            # Double-click → trigger edit label via parent
            parent = self.parent()
            if parent and hasattr(parent, 'edit_label'):
                parent.edit_label()

    def wheelEvent(self, ev):
        if ev.modifiers() & Qt.ControlModifier:
            self.zoomRequest.emit(ev.angleDelta().y())
        else:
            orientation = (Qt.Horizontal
                           if ev.modifiers() & Qt.ShiftModifier
                           else Qt.Vertical)
            self.scrollRequest.emit(ev.angleDelta().y(), orientation)
        ev.accept()

    # ── paint ────────────────────────────────────────────────────────────────
    def sizeHint(self):
        if self.pixmap:
            return QSize(
                int(self.pixmap.width()  * self.scale),
                int(self.pixmap.height() * self.scale),
            )
        return QSize(640, 480)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, event):
        if self.pixmap is None:
            super().paintEvent(event)
            return

        # Update Shape class-level drawing hints
        Shape.scale          = self.scale
        Shape.label_font_size = self.label_font_size

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # Scale coordinate system so all shape coords are in image space
        p.scale(self.scale, self.scale)

        # Draw the image
        p.drawPixmap(0, 0, self.pixmap)

        # Verification overlay
        if self.verified:
            p.setBrush(QBrush(QColor(0, 255, 0, 18)))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))

        # Draw all shapes
        for shape in self.shapes:
            if shape is self.selected_shape:
                continue
            shape.paint(p, selected=False, draw_handles=False)

        # Draw selected shape on top with handles
        if self.selected_shape:
            self.selected_shape.paint(p, selected=True, draw_handles=True)

        # Draw shape in progress
        if self.current and len(self.current.points) == 2:
            r   = QRectF(self.current.points[0], self.current.points[1]).normalized()
            pen = QPen(self._drawing_color, max(1, int(2 / self.scale)), Qt.DashLine)
            p.setPen(pen)
            fill = QColor(self._drawing_color)
            fill.setAlpha(40)
            p.setBrush(fill)
            p.drawRect(r)

        p.end()
