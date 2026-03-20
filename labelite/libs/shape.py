"""Bounding-box Shape with class-aware colours and paint support."""
import copy

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QColor, QPen, QBrush, QFont, QPainterPath, QPainter

DEFAULT_LINE_COLOR = QColor(0, 255, 0, 200)
DEFAULT_FILL_COLOR = QColor(0, 255, 0,  80)

HANDLE_SIZE   = 8      # pixels at 100 % zoom
HANDLE_COLOR  = QColor(255, 255, 255, 230)
HANDLE_BORDER = QColor(  0,   0,   0, 200)

# Class-variable shared by all Shape instances so Canvas can set it once.
# Canvas updates these before each paintEvent.
_scale         = 1.0
_label_font_sz = 12


class Shape:
    # Class-level drawing configuration (set by Canvas before painting)
    line_color  = DEFAULT_LINE_COLOR
    fill_color  = DEFAULT_FILL_COLOR
    scale       = 1.0
    label_font_size = 12
    difficult   = False

    def __init__(self, label=''):
        self.label      = label
        self.points     = []          # list[QPointF] in image space, 4 corners TL TR BR BL
        self.line_color = QColor(DEFAULT_LINE_COLOR)
        self.fill_color = QColor(DEFAULT_FILL_COLOR)
        self.difficult  = False
        self.paint_label = False
        self._closed    = False
        self.visible    = True

    # ── geometry ─────────────────────────────────────────────────────────────
    def add_point(self, point):
        self.points.append(point)

    def close(self):
        self._closed = True

    def bounding_rect(self):
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        return QRectF(QPointF(min(xs), min(ys)), QPointF(max(xs), max(ys)))

    def contains_point(self, point):
        return self.bounding_rect().contains(point)

    def get_handles(self):
        """Return 8 handle positions (image coords): TL TC TR RC BR BC BL LC."""
        r = self.bounding_rect()
        tl = r.topLeft()
        tr = r.topRight()
        br = r.bottomRight()
        bl = r.bottomLeft()
        tc = QPointF((tl.x() + tr.x()) / 2, tl.y())
        bc = QPointF((bl.x() + br.x()) / 2, bl.y())
        lc = QPointF(tl.x(), (tl.y() + bl.y()) / 2)
        rc = QPointF(tr.x(), (tr.y() + br.y()) / 2)
        return [tl, tc, tr, rc, br, bc, bl, lc]

    # ── painting ─────────────────────────────────────────────────────────────
    def paint(self, painter, selected=False, draw_handles=False):
        if not self.points or not self.visible:
            return

        # ── box outline ──
        line_w = max(1, int(round(2.0 / Shape.scale)))
        pen = QPen(self.line_color, line_w)
        if selected:
            pen.setStyle(Qt.DashLine)
        painter.setPen(pen)

        fill = QColor(self.fill_color)
        fill.setAlpha(70 if selected else 50)
        painter.setBrush(QBrush(fill))

        if len(self.points) >= 2:
            r = self.bounding_rect()
            painter.drawRect(r)

        # ── label text ──
        if self.paint_label and self.label and self.points:
            r = self.bounding_rect()
            text_size = max(6, int(Shape.label_font_size / Shape.scale))
            font = QFont()
            font.setPixelSize(text_size)
            font.setBold(True)
            painter.setFont(font)

            # Background pill behind the text
            fm   = painter.fontMetrics()
            tw   = fm.horizontalAdvance(self.label)
            th   = fm.height()
            tx   = r.x()
            ty   = r.y() - th - 2
            bg   = QColor(self.line_color)
            bg.setAlpha(180)
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRect(QRectF(tx, ty, tw + 4, th + 2))

            painter.setPen(QColor('white'))
            painter.drawText(QPointF(tx + 2, ty + th - 1), self.label)

        # ── resize handles ──
        if draw_handles:
            handle_r = HANDLE_SIZE / Shape.scale / 2
            for h in self.get_handles():
                painter.setPen(QPen(HANDLE_BORDER, max(1, 1 / Shape.scale)))
                painter.setBrush(HANDLE_COLOR)
                painter.drawEllipse(h, handle_r, handle_r)

    def __copy__(self):
        s = Shape(label=self.label)
        s.points     = [QPointF(p) for p in self.points]
        s.line_color = QColor(self.line_color)
        s.fill_color = QColor(self.fill_color)
        s.difficult  = self.difficult
        s.paint_label = self.paint_label
        s._closed    = self._closed
        s.visible    = self.visible
        return s

    def __deepcopy__(self, memo):
        return self.__copy__()
