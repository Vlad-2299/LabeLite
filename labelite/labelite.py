#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
LabLite – Graphical image annotation tool for YOLO / Pascal VOC / CreateML.
"""
import argparse
import codecs
import os
import os.path
import platform
import re
import sys
sys.path.insert(0, os.path.dirname(__file__))
import subprocess
import shutil
import webbrowser as wb

from functools import partial
from collections import defaultdict

from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from libs.combobox              import ComboBox
from libs.resources             import *          # noqa
from libs.constants             import *
from libs.utils                 import (new_icon, new_action, add_actions,
                                        have_qstring, format_shortcut,
                                        natural_sort, generate_color_by_text,
                                        Struct, CLASS_COLORS)
from libs.settings              import Settings
from libs.shape                 import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.stringBundle          import StringBundle
from libs.canvas                import Canvas
from libs.zoomWidget            import ZoomWidget
from libs.labelDialog           import LabelDialog
from libs.colorDialog           import ColorDialog
from libs.labelFile             import LabelFile, LabelFileError, LabelFileFormat
from libs.toolBar               import ToolBar
from libs.pascal_voc_io         import PascalVocReader
from libs.pascal_voc_io         import XML_EXT
from libs.yolo_io               import YoloReader
from libs.yolo_io               import TXT_EXT
from libs.create_ml_io          import CreateMLReader
from libs.create_ml_io          import JSON_EXT
from libs.ustr                  import ustr
from libs.hashableQListWidgetItem import HashableQListWidgetItem

__appname__ = 'LabeLite'


# ══════════════════════════════════════════════════════════════════════════════
# Command Pattern
# ══════════════════════════════════════════════════════════════════════════════

class Command:
    def execute(self): raise NotImplementedError
    def undo(self):    raise NotImplementedError


class CommandHistory:
    def __init__(self, max_history: int = 100):
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._max = max_history

    def push(self, cmd: Command, execute: bool = True):
        if execute:
            cmd.execute()
        if len(self._undo) >= self._max:
            self._undo.pop(0)
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self):
        if self._undo:
            cmd = self._undo.pop()
            cmd.undo()
            self._redo.append(cmd)

    def redo(self):
        if self._redo:
            cmd = self._redo.pop()
            cmd.execute()
            self._undo.append(cmd)

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    @property
    def can_undo(self): return bool(self._undo)
    @property
    def can_redo(self): return bool(self._redo)


class AddShapeCommand(Command):
    def __init__(self, mw, shape):
        self.mw = mw; self.shape = shape

    def execute(self):
        if self.shape not in self.mw.canvas.shapes:
            self.mw.canvas.shapes.append(self.shape)
        self.mw.add_label(self.shape)
        self.mw.canvas.update()
        self.mw.set_dirty()

    def undo(self):
        if self.shape in self.mw.canvas.shapes:
            self.mw.canvas.shapes.remove(self.shape)
        self.mw.remove_label(self.shape)
        if self.mw.canvas.selected_shape is self.shape:
            self.mw.canvas.selected_shape = None
        self.mw.canvas.update()
        self.mw.set_dirty()


class DeleteShapeCommand(Command):
    def __init__(self, mw, shape):
        self.mw = mw; self.shape = shape

    def execute(self):
        if self.shape in self.mw.canvas.shapes:
            self.mw.canvas.shapes.remove(self.shape)
        self.mw.remove_label(self.shape)
        if self.mw.canvas.selected_shape is self.shape:
            self.mw.canvas.selected_shape = None
        self.mw.canvas.update()
        self.mw.set_dirty()

    def undo(self):
        self.mw.canvas.shapes.append(self.shape)
        self.mw.add_label(self.shape)
        self.mw.canvas.update()
        self.mw.set_dirty()


class MoveShapeCommand(Command):
    def __init__(self, canvas, shape, old_pts, new_pts):
        self.canvas = canvas; self.shape = shape
        self.old_pts = [QPointF(p) for p in old_pts]
        self.new_pts = [QPointF(p) for p in new_pts]

    def execute(self):
        self.shape.points = [QPointF(p) for p in self.new_pts]
        self.canvas.update()

    def undo(self):
        self.shape.points = [QPointF(p) for p in self.old_pts]
        self.canvas.update()


class RelabelShapeCommand(Command):
    def __init__(self, mw, shape, old_label, new_label):
        self.mw = mw; self.shape = shape
        self.old_label = old_label; self.new_label = new_label

    def _apply(self, label):
        self.shape.label      = label
        self.shape.line_color = self.mw.class_colors.get(label, generate_color_by_text(label))
        self.shape.fill_color = self.shape.line_color
        item = self.mw.shapes_to_items.get(self.shape)
        if item:
            item.setText(label)
            item.setIcon(self.mw._class_icon(label))
        self.mw.canvas.update()
        self.mw.set_dirty()
        self.mw._update_class_counts()

    def execute(self): self._apply(self.new_label)
    def undo(self):    self._apply(self.old_label)


# ══════════════════════════════════════════════════════════════════════════════
# Window helpers
# ══════════════════════════════════════════════════════════════════════════════

class WindowMixin:
    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            add_actions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(f'{title}ToolBar')
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        if actions:
            add_actions(toolbar, actions)
        self.addToolBar(Qt.TopToolBarArea, toolbar)
        return toolbar


# ══════════════════════════════════════════════════════════════════════════════
# Main window
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, default_filename=None,
                 default_prefdef_class_file=None,
                 default_save_dir=None):
        super().__init__()
        self.setWindowTitle(__appname__)

        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        self.os_name = platform.system()
        self.string_bundle = StringBundle.get_bundle()
        get_str = lambda str_id: self.string_bundle.get_string(str_id)

        self.default_save_dir  = default_save_dir
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT,
                                              LabelFileFormat.YOLO)
        LabelFile.suffix = {
            LabelFileFormat.PASCAL_VOC: XML_EXT,
            LabelFileFormat.YOLO:       TXT_EXT,
            LabelFileFormat.CREATE_ML:  JSON_EXT,
        }.get(self.label_file_format, TXT_EXT)
        self.m_img_list    = []
        self.dir_name      = None
        self.label_hist    = []
        self.last_open_dir = None
        self.cur_img_idx   = 0
        self.img_count     = 1
        self.dirty         = False
        self._no_selection_slot = False
        self._beginner     = True
        self.screencast    = 'https://github.com/tzutalin/labelImg'
        self._clipboard_shape = None   # shape held by Ctrl+C

        # Verified images (path → bool, stored in-memory only)
        self.verified_images: set[str] = set()

        # Per-class colour overrides (initialised from CLASS_COLORS defaults)
        self.class_colors: dict[str, QColor] = {
            k: QColor(v) for k, v in CLASS_COLORS.items()
        }

        # Undo / redo
        self.history = CommandHistory()

        # Pre-defined classes
        self.load_predefined_classes(default_prefdef_class_file)

        # Core state
        self.label_dialog = LabelDialog(parent=self, list_item=self.label_hist)
        self.items_to_shapes: dict = {}
        self.shapes_to_items: dict = {}
        self.prev_label_text = ''

        # ── Build the "Annotations" dock ──────────────────────────────────────
        dock_root = QWidget()
        dock_layout = QVBoxLayout(dock_root)
        dock_layout.setContentsMargins(4, 4, 4, 4)
        dock_layout.setSpacing(4)

        # ── Classes section ──────────────────────────────────────────────────
        classes_lbl = QLabel('Classes')
        classes_lbl.setStyleSheet('font-weight: bold;')
        dock_layout.addWidget(classes_lbl)

        self.class_table = QTableWidget(0, 4)
        self.class_table.setHorizontalHeaderLabels(['ID', 'Name', 'Count', 'Color'])
        self.class_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents)
        self.class_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        self.class_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        self.class_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Fixed)
        self.class_table.setColumnWidth(3, 54)
        self.class_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.class_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.class_table.verticalHeader().setVisible(False)
        self.class_table.setMaximumHeight(160)
        self.class_table.setAlternatingRowColors(True)
        dock_layout.addWidget(self.class_table)

        # ── Bounding-boxes section ────────────────────────────────────────────
        boxes_hdr = QHBoxLayout()
        boxes_lbl = QLabel('Bounding Boxes')
        boxes_lbl.setStyleSheet('font-weight: bold;')
        boxes_hdr.addWidget(boxes_lbl)
        boxes_hdr.addStretch()
        self.display_label_option = QAction(get_str('displayLabel'), self)
        self.display_label_option.setShortcut('Ctrl+Shift+P')
        self.display_label_option.setCheckable(True)
        self.display_label_option.setChecked(
            settings.get(SETTING_PAINT_LABEL, False))
        self.display_label_option.triggered.connect(self.toggle_paint_labels_option)
        lbl_toggle_btn = QToolButton()
        lbl_toggle_btn.setDefaultAction(self.display_label_option)
        lbl_toggle_btn.setToolTip('Show/hide class labels on boxes')
        boxes_hdr.addWidget(lbl_toggle_btn)
        boxes_hdr_w = QWidget()
        boxes_hdr_w.setLayout(boxes_hdr)
        dock_layout.addWidget(boxes_hdr_w)

        self.bbox_list = QListWidget()
        self.bbox_list.itemSelectionChanged.connect(self._on_bbox_selection_changed)
        self.bbox_list.itemChanged.connect(self._on_bbox_item_changed)
        self.bbox_list.itemDoubleClicked.connect(self.change_selected_label)
        dock_layout.addWidget(self.bbox_list)

        self.dock = QDockWidget('Annotations', self)
        self.dock.setObjectName('annotationsDock')
        self.dock.setWidget(dock_root)

        # ── File list dock ────────────────────────────────────────────────────
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemDoubleClicked.connect(
            self.file_item_double_clicked)
        file_list_layout = QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addWidget(self.file_list_widget)
        file_list_container = QWidget()
        file_list_container.setLayout(file_list_layout)
        self.file_dock = QDockWidget(get_str('fileList'), self)
        self.file_dock.setObjectName(get_str('files'))
        self.file_dock.setWidget(file_list_container)

        # ── Canvas ────────────────────────────────────────────────────────────
        self.zoom_widget  = ZoomWidget()
        self.color_dialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.zoomRequest.connect(self.zoom_request)
        self.canvas.set_drawing_shape_to_square(
            settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scroll_bars = {
            Qt.Vertical:   scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar(),
        }
        self.scroll_area = scroll
        self.canvas.scrollRequest.connect(self.scroll_request)
        self.canvas.installEventFilter(self)
        self.last_pan_pos = None

        self.canvas.newShape.connect(self.new_shape)
        self.canvas.shapeMoved.connect(self.on_shape_moved)
        self.canvas.selectionChanged.connect(self.shape_selection_changed)
        self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)
        self.file_dock.setFeatures(QDockWidget.DockWidgetFloatable)

        self.dock_features = (QDockWidget.DockWidgetClosable |
                              QDockWidget.DockWidgetFloatable)
        self.dock.setFeatures(self.dock.features() ^ self.dock_features)

        # ── Actions ───────────────────────────────────────────────────────────
        action = partial(new_action, self)

        quit_act = action(get_str('quit'),   self.close,
                          'Ctrl+Q', 'quit',  get_str('quitApp'))
        open_act = action(get_str('openFile'), self.open_file,
                          'Ctrl+O', 'open',  get_str('openFileDetail'))
        open_dir = action(get_str('openDir'), self.open_dir_dialog,
                          'Ctrl+u', 'open',  get_str('openDir'))
        change_save_dir = action(get_str('changeSaveDir'),
                                 self.change_save_dir_dialog,
                                 'Ctrl+r', 'open',
                                 get_str('changeSavedAnnotationDir'))
        open_annotation = action(get_str('openAnnotation'),
                                 self.open_annotation_dialog,
                                 'Ctrl+Shift+O', 'open',
                                 get_str('openAnnotationDetail'))
        copy_prev_bounding = action(get_str('copyPrevBounding'),
                                    self.copy_previous_bounding_boxes,
                                    None, 'copy',
                                    get_str('copyPrevBounding'))
        open_next_image = action(get_str('nextImg'), self.open_next_image,
                                 'd', 'next', get_str('nextImgDetail'))
        open_prev_image = action(get_str('prevImg'), self.open_prev_image,
                                 'a', 'prev', get_str('prevImgDetail'))
        verify = action(get_str('verifyImg'), self.verify_image,
                        'space', 'verify', get_str('verifyImgDetail'))
        save   = action(get_str('save'),    self.save_file,
                        'Ctrl+S', 'save',  get_str('saveDetail'),
                        enabled=False)

        def get_format_meta(fmt):
            if fmt == LabelFileFormat.PASCAL_VOC: return '&PascalVOC',  'format_voc'
            if fmt == LabelFileFormat.YOLO:       return '&YOLO',       'format_yolo'
            if fmt == LabelFileFormat.CREATE_ML:  return '&CreateML',   'format_createml'
            return '&Unknown', 'format_voc'

        save_format = action(
            get_format_meta(self.label_file_format)[0],
            self.change_format, 'Ctrl+`',
            get_format_meta(self.label_file_format)[1],
            get_str('changeSaveFormat'), enabled=True)

        save_as  = action(get_str('saveAs'),   self.save_file_as,
                          'Ctrl+Shift+S', 'save-as',
                          get_str('saveAsDetail'), enabled=False)
        close    = action(get_str('closeCur'), self.close_file,
                          'Ctrl+W', 'close', get_str('closeCurDetail'))
        delete_image = action(get_str('deleteImg'), self.delete_image,
                              'Ctrl+Shift+D', 'close',
                              get_str('deleteImgDetail'))
        reset_all = action(get_str('resetAll'), self.reset_all,
                           None, 'resetall', get_str('resetAllDetail'))

        color1 = action(get_str('boxLineColor'), self.choose_color1,
                        'Ctrl+L', 'color_line', get_str('boxLineColorDetail'))

        create_mode = action(get_str('crtBox'),  self.set_create_mode,
                             'w', 'new',  get_str('crtBoxDetail'), enabled=False)
        edit_mode   = action(get_str('editBox'), self.set_edit_mode,
                             'Ctrl+J', 'edit', get_str('editBoxDetail'), enabled=False)

        create = action(get_str('crtBox'),  self.create_shape,
                        'w', 'new',  get_str('crtBoxDetail'), enabled=False)
        delete = action(get_str('delBox'),  self.delete_selected_shape,
                        'Delete', 'delete', get_str('delBoxDetail'), enabled=False)
        copy   = action(get_str('dupBox'),  self.copy_shape_to_clipboard,
                        'Ctrl+C', 'copy',   get_str('dupBoxDetail'), enabled=False)
        paste  = action('Paste Box',        self.paste_shape_from_clipboard,
                        'Ctrl+V', 'copy',   'Paste copied box', enabled=True)

        advanced_mode = action(get_str('advancedMode'), self.toggle_advanced_mode,
                               'Ctrl+Shift+A', 'expert',
                               get_str('advancedModeDetail'), checkable=True)

        hide_all = action(get_str('hideAllBox'),
                          partial(self.toggle_polygons, False),
                          'Ctrl+H', 'hide', get_str('hideAllBoxDetail'),
                          enabled=False)
        show_all = action(get_str('showAllBox'),
                          partial(self.toggle_polygons, True),
                          'Ctrl+A', 'hide', get_str('showAllBoxDetail'),
                          enabled=False)

        help_default  = action(get_str('tutorialDefault'),
                               self.show_default_tutorial_dialog,
                               None, 'help', get_str('tutorialDetail'))
        show_info     = action(get_str('info'),  self.show_info_dialog,
                               None, 'help', get_str('info'))
        show_shortcut = action(get_str('shortcut'), self.show_shortcuts_dialog,
                               None, 'help', get_str('shortcut'))

        undo = action(get_str('undo'), self.undo_action,
                      'Ctrl+Z', 'undo', get_str('undoDetail'), enabled=True)
        redo = action(get_str('redo'), self.redo_action,
                      'Ctrl+Y', 'redo', get_str('redoDetail'), enabled=True)

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)
        self.zoom_widget.setEnabled(False)

        zoom_in  = action(get_str('zoomin'),  partial(self.add_zoom,  10),
                          'Ctrl++', 'zoom-in',  get_str('zoominDetail'),  enabled=False)
        zoom_out = action(get_str('zoomout'), partial(self.add_zoom, -10),
                          'Ctrl+-', 'zoom-out', get_str('zoomoutDetail'), enabled=False)
        zoom_org = action(get_str('originalsize'), partial(self.set_zoom, 100),
                          'Ctrl+=', 'zoom', get_str('originalsizeDetail'), enabled=False)
        fit_window = action(get_str('fitWin'), self.set_fit_window,
                            'Ctrl+F', 'fit-window', get_str('fitWinDetail'),
                            checkable=True, enabled=False)
        fit_width  = action(get_str('fitWidth'), self.set_fit_width,
                            'Ctrl+Shift+F', 'fit-width', get_str('fitWidthDetail'),
                            checkable=True, enabled=False)

        zoom_actions = (self.zoom_widget, zoom_in, zoom_out,
                        zoom_org, fit_window, fit_width)
        self.zoom_mode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW:  self.scale_fit_window,
            self.FIT_WIDTH:   self.scale_fit_width,
            self.MANUAL_ZOOM: lambda: 1,
        }

        edit = action(get_str('editLabel'), self.change_selected_label,
                      'Ctrl+E', 'edit', get_str('editLabelDetail'), enabled=False)

        shape_line_color = action(get_str('shapeLineColor'),
                                  self.choose_shape_line_color,
                                  icon='color_line',
                                  tip=get_str('shapeLineColorDetail'),
                                  enabled=False)
        shape_fill_color = action(get_str('shapeFillColor'),
                                  self.choose_shape_fill_color,
                                  icon='color',
                                  tip=get_str('shapeFillColorDetail'),
                                  enabled=False)

        labels_panel = self.dock.toggleViewAction()
        labels_panel.setText(get_str('showHide'))
        labels_panel.setShortcut('Ctrl+Shift+L')

        # bbox list context menu
        bbox_menu = QMenu()
        add_actions(bbox_menu, (edit, delete))
        self.bbox_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.bbox_list.customContextMenuRequested.connect(
            lambda pt: bbox_menu.exec_(self.bbox_list.mapToGlobal(pt)))

        self.draw_squares_option = QAction(get_str('drawSquares'), self)
        self.draw_squares_option.setShortcut('Ctrl+Shift+R')
        self.draw_squares_option.setCheckable(True)
        self.draw_squares_option.setChecked(
            settings.get(SETTING_DRAW_SQUARE, False))
        self.draw_squares_option.triggered.connect(self.toggle_draw_square)

        self.actions = Struct(
            save=save, save_format=save_format, saveAs=save_as,
            open=open_act, close=close, resetAll=reset_all,
            deleteImg=delete_image,
            lineColor=color1,
            create=create, delete=delete, edit=edit, copy=copy, paste=paste,
            createMode=create_mode, editMode=edit_mode,
            advancedMode=advanced_mode,
            shapeLineColor=shape_line_color, shapeFillColor=shape_fill_color,
            zoom=zoom, zoomIn=zoom_in, zoomOut=zoom_out, zoomOrg=zoom_org,
            fitWindow=fit_window, fitWidth=fit_width,
            zoomActions=zoom_actions,
            undo=undo, redo=redo,
            fileMenuActions=(open_act, open_dir, save, save_as,
                             close, reset_all, quit_act),
            beginner=(), advanced=(),
            editMenu=(edit, copy, paste, delete, None, color1,
                      self.draw_squares_option, None, undo, redo),
            beginnerContext=(create, edit, copy, paste, delete),
            advancedContext=(create_mode, edit_mode, edit, copy, paste, delete,
                             shape_line_color, shape_fill_color),
            onLoadActive=(close, create, create_mode, edit_mode),
            onShapesPresent=(save_as, hide_all, show_all),
        )

        self.menus = Struct(
            file=self.menu(get_str('menu_file')),
            edit=self.menu(get_str('menu_edit')),
            view=self.menu(get_str('menu_view')),
            help=self.menu(get_str('menu_help')),
            recentFiles=QMenu(get_str('menu_openRecent')),
        )

        self.auto_saving = QAction(get_str('autoSaveMode'), self)
        self.auto_saving.setCheckable(True)
        self.auto_saving.setChecked(settings.get(SETTING_AUTO_SAVE, False))

        self.single_class_mode = QAction(get_str('singleClsMode'), self)
        self.single_class_mode.setShortcut('Ctrl+Shift+S')
        self.single_class_mode.setCheckable(True)
        self.single_class_mode.setChecked(
            settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None

        add_actions(self.menus.file,
                    (open_act, open_dir, change_save_dir, open_annotation,
                     copy_prev_bounding, self.menus.recentFiles,
                     save, save_format, save_as, close,
                     reset_all, delete_image, quit_act))
        add_actions(self.menus.help, (help_default, show_info, show_shortcut))
        add_actions(self.menus.view, (
            self.auto_saving, self.single_class_mode,
            self.display_label_option, labels_panel, advanced_mode, None,
            hide_all, show_all, None,
            zoom_in, zoom_out, zoom_org, None,
            fit_window, fit_width))

        self.menus.file.aboutToShow.connect(self.update_file_menu)

        # Canvas context menus
        add_actions(self.canvas.menus[0], self.actions.beginnerContext)
        # Shape right-click menu: Change Label + Delete
        add_actions(self.canvas.menus[1], (
            action('Change &Label', self.change_selected_label,
                   icon='edit', tip='Rename this bounding box'),
            None,
            action('&Delete Box', self.delete_selected_shape,
                   icon='delete', tip='Delete this bounding box'),
        ))

        self.tools = self.toolbar('Tools')
        self.actions.beginner = (
            open_prev_image, open_next_image, verify,
            save, save_format, None,
            create, copy, paste, delete, None,
            undo, redo, None,
            zoom_in, zoom, zoom_out, fit_window,
        )
        self.actions.advanced = (
            open_prev_image, open_next_image,
            save, save_format, None,
            create_mode, edit_mode, None,
            undo, redo, None,
            hide_all, show_all,
        )

        self.statusBar().showMessage(f'{__appname__} started.')
        self.statusBar().show()

        # ── Application state ─────────────────────────────────────────────────
        self.image          = QImage()
        self.file_path      = ustr(default_filename)
        self.last_open_dir  = None
        self.recent_files   = []
        self.max_recent     = 7
        self.line_color     = None
        self.fill_color     = None
        self.zoom_level     = 100
        self.difficult      = False

        if settings.get(SETTING_RECENT_FILES):
            self.recent_files = list(settings.get(SETTING_RECENT_FILES))

        size           = settings.get(SETTING_WIN_SIZE,  QSize(600, 500))
        saved_position = settings.get(SETTING_WIN_POSE, QPoint(0, 0))
        position       = QPoint(0, 0)
        for screen in QApplication.screens():
            if screen.availableGeometry().contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)

        save_dir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.last_open_dir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if self.default_save_dir is None and save_dir and os.path.exists(save_dir):
            self.default_save_dir = save_dir

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.line_color = QColor(
            settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fill_color = QColor(
            settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.set_drawing_color(self.line_color)
        Shape.difficult = self.difficult

        if settings.get(SETTING_ADVANCE_MODE, False):
            self.actions.advancedMode.setChecked(True)
            self.toggle_advanced_mode()

        self.update_file_menu()

        if self.file_path and os.path.isdir(self.file_path):
            self.queue_event(partial(self.import_dir_images, self.file_path or ''))
        elif self.file_path:
            self.queue_event(partial(self.load_file, self.file_path or ''))

        self.zoom_widget.valueChanged.connect(self.paint_canvas)
        self.populate_mode_actions()

        self.label_coordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.label_coordinates)

        if self.file_path and os.path.isdir(self.file_path):
            self.open_dir_dialog(dir_path=self.file_path, silent=True)

    # ══════════════════════════════════════════════════════════════════════════
    # Class table management
    # ══════════════════════════════════════════════════════════════════════════

    def _class_icon(self, label: str) -> QIcon:
        """Return a small solid-colour square icon for a class label."""
        color = self.class_colors.get(label, generate_color_by_text(label))
        pix   = QPixmap(14, 14)
        pix.fill(color)
        return QIcon(pix)

    def _populate_class_table(self):
        """Rebuild the class table from label_hist."""
        self.class_table.blockSignals(True)
        self.class_table.setRowCount(0)
        for class_id, label in enumerate(self.label_hist):
            self._add_class_table_row(class_id, label)
        self.class_table.blockSignals(False)
        self._update_class_counts()

    def _update_class_counts(self):
        """Update the Count column in the class table from current canvas shapes."""
        counts: dict[str, int] = {}
        for shape in self.canvas.shapes:
            counts[shape.label] = counts.get(shape.label, 0) + 1
        for row in range(self.class_table.rowCount()):
            name_item = self.class_table.item(row, 1)
            if name_item:
                count = counts.get(name_item.text(), 0)
                count_item = self.class_table.item(row, 2)
                if count_item:
                    count_item.setText(str(count))

    def _add_class_table_row(self, class_id: int, label: str):
        """Append one row to the class table without triggering itemChanged."""
        self.class_table.blockSignals(True)
        row = self.class_table.rowCount()
        self.class_table.insertRow(row)

        # ID column – not editable
        id_item = QTableWidgetItem(str(class_id))
        id_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        id_item.setTextAlignment(Qt.AlignCenter)
        self.class_table.setItem(row, 0, id_item)

        # Name column – read-only (source of truth is classes.txt)
        name_item = QTableWidgetItem(label)
        name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.class_table.setItem(row, 1, name_item)

        # Count column – read-only, shows number of annotations for this class
        count_item = QTableWidgetItem('0')
        count_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        count_item.setTextAlignment(Qt.AlignCenter)
        self.class_table.setItem(row, 2, count_item)

        # Color column – clickable button
        color = self.class_colors.get(label, generate_color_by_text(label))
        btn   = QPushButton()
        btn.setFixedHeight(22)
        btn.setStyleSheet(self._color_btn_style(color))
        btn.clicked.connect(lambda checked, cid=class_id: self._pick_class_color(cid))
        self.class_table.setCellWidget(row, 3, btn)

        self.class_table.blockSignals(False)

    @staticmethod
    def _color_btn_style(color: QColor) -> str:
        return (f'background-color: rgba({color.red()},{color.green()},'
                f'{color.blue()},{color.alpha()});'
                'border: 1px solid #555; border-radius: 2px;')

    def _ensure_class_in_table(self, label: str):
        """Add *label* to label_hist and the class table if not already present."""
        if label not in self.label_hist:
            self.label_hist.append(label)
        class_id = self.label_hist.index(label)
        # Check if already in the table
        for row in range(self.class_table.rowCount()):
            name_item = self.class_table.item(row, 1)
            if name_item and name_item.text() == label:
                return
        self._add_class_table_row(class_id, label)

    def _load_classes_txt(self, annotation_dir: str):
        """Read classes.txt from annotation_dir and sync label_hist + class table."""
        classes_path = os.path.join(annotation_dir, 'classes.txt')
        if not os.path.isfile(classes_path):
            return
        with open(classes_path, 'r', encoding='utf-8') as f:
            names = [ln.strip() for ln in f if ln.strip()]
        if not names or names == self.label_hist:
            return
        self.label_hist = names
        self._populate_class_table()
        print('[Classes]', '  '.join(f'{i}:{n}' for i, n in enumerate(names)))

    def _pick_class_color(self, class_id: int):
        """Open a colour picker for the given class_id."""
        if class_id >= len(self.label_hist):
            return
        label   = self.label_hist[class_id]
        current = self.class_colors.get(label, generate_color_by_text(label))
        color   = self.color_dialog.getColor(current,
                                             f'Color for "{label}"',
                                             default=current)
        if not color:
            return

        self.class_colors[label] = color

        # Update button in table
        for row in range(self.class_table.rowCount()):
            id_item = self.class_table.item(row, 0)
            if id_item and int(id_item.text()) == class_id:
                btn = self.class_table.cellWidget(row, 3)
                if btn:
                    btn.setStyleSheet(self._color_btn_style(color))
                break

        # Update all shapes of this class
        for shape in self.canvas.shapes:
            if shape.label == label:
                shape.line_color = color
                shape.fill_color = color

        # Update bbox list icons
        for item, shape in self.items_to_shapes.items():
            if shape.label == label:
                item.setIcon(self._class_icon(label))

        self.canvas.update()
        self.set_dirty()

    # ══════════════════════════════════════════════════════════════════════════
    # Bbox list management
    # ══════════════════════════════════════════════════════════════════════════

    def add_label(self, shape):
        shape.paint_label = self.display_label_option.isChecked()
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setIcon(self._class_icon(shape.label))
        self.items_to_shapes[item]  = shape
        self.shapes_to_items[shape] = item
        self.bbox_list.addItem(item)
        for act in self.actions.onShapesPresent:
            act.setEnabled(True)
        self._ensure_class_in_table(shape.label)
        self._update_class_counts()

    def remove_label(self, shape):
        if shape is None:
            return
        item = self.shapes_to_items.get(shape)
        if item is None:
            return
        self.bbox_list.takeItem(self.bbox_list.row(item))
        del self.shapes_to_items[shape]
        del self.items_to_shapes[item]
        self._update_class_counts()

    def _on_bbox_selection_changed(self):
        """Bbox list selection → select the corresponding shape on canvas."""
        if self._no_selection_slot:
            self._no_selection_slot = False
            return
        selected = self.bbox_list.selectedItems()
        if selected:
            shape = self.items_to_shapes.get(selected[0])
            if shape:
                self._no_selection_slot = True
                self.canvas.select_shape(shape)
                self.canvas.update()

    def _on_bbox_item_changed(self, item):
        """Checkbox toggled → toggle shape visibility."""
        shape = self.items_to_shapes.get(item)
        if shape:
            self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)

    def current_item(self):
        items = self.bbox_list.selectedItems()
        return items[0] if items else None

    # ══════════════════════════════════════════════════════════════════════════
    # Key events / event filter
    # ══════════════════════════════════════════════════════════════════════════

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(False)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(True)
        elif key == Qt.Key_Escape and not self.canvas.editing():
            # Cancel drawing regardless of which widget has focus
            self.canvas.current = None
            self.canvas.set_editing(True)
            self.canvas.update()
            self.actions.create.setEnabled(True)

    def eventFilter(self, source, event):
        if source is self.canvas:
            if (event.type() == QEvent.MouseButtonPress
                    and event.button() == Qt.MiddleButton):
                self.last_pan_pos = QCursor.pos()
                return True
            elif (event.type() == QEvent.MouseMove
                  and (event.buttons() & Qt.MiddleButton)):
                if self.last_pan_pos is not None:
                    cur = QCursor.pos()
                    dx  = cur.x() - self.last_pan_pos.x()
                    dy  = cur.y() - self.last_pan_pos.y()
                    if dx == 0 and dy == 0:
                        return True
                    self.last_pan_pos = cur
                    self.scroll_bars[Qt.Horizontal].setValue(
                        self.scroll_bars[Qt.Horizontal].value() - dx)
                    self.scroll_bars[Qt.Vertical].setValue(
                        self.scroll_bars[Qt.Vertical].value() - dy)
                return True
            elif (event.type() == QEvent.MouseButtonRelease
                  and event.button() == Qt.MiddleButton):
                self.last_pan_pos = None
                return True
        return super().eventFilter(source, event)

    # ══════════════════════════════════════════════════════════════════════════
    # Undo / redo
    # ══════════════════════════════════════════════════════════════════════════

    def undo_action(self): self.history.undo()
    def redo_action(self): self.history.redo()

    def on_shape_moved(self, shape, old_points, new_points):
        self.history.push(MoveShapeCommand(self.canvas, shape,
                                           old_points, new_points),
                          execute=False)
        self.set_dirty()

    # ══════════════════════════════════════════════════════════════════════════
    # Verify image – just toggles a checkmark on the file list item
    # ══════════════════════════════════════════════════════════════════════════

    def verify_image(self, _value=False):
        if self.file_path is None:
            return
        if self.file_path in self.verified_images:
            self.verified_images.discard(self.file_path)
            self.canvas.verified = False
        else:
            self.verified_images.add(self.file_path)
            self.canvas.verified = True
        self._update_file_verify_icon(self.file_path)
        self.canvas.update()
        state = 'verified' if self.canvas.verified else 'unverified'
        self.status(f'Image {state}')

    def _update_file_verify_icon(self, file_path: str):
        if file_path and file_path in self.m_img_list:
            idx  = self.m_img_list.index(file_path)
            item = self.file_list_widget.item(idx)
            if item:
                state = (Qt.Checked if file_path in self.verified_images
                         else Qt.Unchecked)
                item.setCheckState(state)

    # ══════════════════════════════════════════════════════════════════════════
    # Format helpers
    # ══════════════════════════════════════════════════════════════════════════

    def set_format(self, save_format):
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(new_icon('format_voc'))
            self.label_file_format = LabelFileFormat.PASCAL_VOC
            LabelFile.suffix = XML_EXT
        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(new_icon('format_yolo'))
            self.label_file_format = LabelFileFormat.YOLO
            LabelFile.suffix = TXT_EXT
        elif save_format == FORMAT_CREATEML:
            self.actions.save_format.setText(FORMAT_CREATEML)
            self.actions.save_format.setIcon(new_icon('format_createml'))
            self.label_file_format = LabelFileFormat.CREATE_ML
            LabelFile.suffix = JSON_EXT

    def change_format(self):
        if   self.label_file_format == LabelFileFormat.PASCAL_VOC: self.set_format(FORMAT_YOLO)
        elif self.label_file_format == LabelFileFormat.YOLO:        self.set_format(FORMAT_CREATEML)
        elif self.label_file_format == LabelFileFormat.CREATE_ML:   self.set_format(FORMAT_PASCALVOC)
        else: raise ValueError('Unknown label file format.')
        self.set_dirty()

    def no_shapes(self):
        return not self.items_to_shapes

    def toggle_advanced_mode(self, value=True):
        self._beginner = not value
        self.canvas.set_editing(True)
        self.populate_mode_actions()
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dock_features)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dock_features)

    def populate_mode_actions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        add_actions(self.tools, tool)
        self.canvas.menus[0].clear()
        add_actions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = ((self.actions.create,)
                   if self.beginner()
                   else (self.actions.createMode, self.actions.editMode))
        add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_beginner(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.beginner)

    def set_advanced(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.advanced)

    def set_dirty(self, *_args):
        self.dirty = True
        self.actions.save.setEnabled(True)

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)

    def toggle_actions(self, value=True):
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for act in self.actions.onLoadActive:
            act.setEnabled(value)

    def queue_event(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def reset_state(self):
        self.items_to_shapes.clear()
        self.shapes_to_items.clear()
        self.bbox_list.clear()
        self.class_table.blockSignals(True)
        self.class_table.setRowCount(0)
        self.class_table.blockSignals(False)
        self.file_path  = None
        self.image_data = None
        self.label_file = None
        self.canvas.reset_state()
        self.label_coordinates.clear()
        self.history.clear()

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, file_path)

    def beginner(self): return self._beginner
    def advanced(self): return not self._beginner

    # ── dialogs ───────────────────────────────────────────────────────────────

    def show_tutorial_dialog(self, browser='default', link=None):
        if link is None:
            link = self.screencast
        wb.open(link, new=2)

    def show_default_tutorial_dialog(self): self.show_tutorial_dialog()

    def show_info_dialog(self):
        from libs import __version__
        QMessageBox.information(self, 'Information',
                                f'Name: {__appname__}\n'
                                f'Version: {__version__}\n'
                                f'Python: {sys.version}')

    def show_shortcuts_dialog(self):
        self.show_tutorial_dialog(
            link='https://github.com/tzutalin/labelImg#Hotkeys')

    # ── shape creation ────────────────────────────────────────────────────────

    def create_shape(self):
        assert self.beginner()
        self.canvas.set_editing(False)
        self.actions.create.setEnabled(False)

    def toggle_drawing_sensitive(self, drawing=True):
        # Called by canvas.drawingPolygon signal – canvas already switched its
        # own mode, so do NOT call canvas.set_editing() here (that would recurse).
        self.actions.editMode.setEnabled(not drawing)
        if not drawing and self.beginner():
            self.actions.create.setEnabled(True)

    def toggle_draw_mode(self, edit=True):
        self.canvas.set_editing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)

    def set_create_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(False)

    def set_edit_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(True)
        self._on_bbox_selection_changed()

    # ── file menu ─────────────────────────────────────────────────────────────

    def update_file_menu(self):
        curr = self.file_path
        menu = self.menus.recentFiles
        menu.clear()
        for i, f in enumerate(f for f in self.recent_files
                               if f != curr and os.path.exists(f)):
            act = QAction(new_icon('labels'),
                          f'&{i + 1} {QFileInfo(f).fileName()}', self)
            act.triggered.connect(partial(self.load_recent, f))
            menu.addAction(act)

    # ── label editing ─────────────────────────────────────────────────────────

    def change_selected_label(self, *_args):
        """Open the label dialog for the currently selected shape."""
        shape = self.canvas.selected_shape
        if not shape:
            # Fall back to bbox list selection
            item = self.current_item()
            if item:
                shape = self.items_to_shapes.get(item)
        if not shape:
            return
        old_label = shape.label
        text      = self.label_dialog.pop_up(old_label)
        if text is not None and text != old_label:
            cmd = RelabelShapeCommand(self, shape, old_label, text)
            self.history.push(cmd)
            self._ensure_class_in_table(text)

    # Keep edit_label as an alias so menu/toolbar action still works
    def edit_label(self, *_args):
        self.change_selected_label()

    def file_item_double_clicked(self, item=None):
        self.cur_img_idx = self.m_img_list.index(ustr(item.text()))
        filename = self.m_img_list[self.cur_img_idx]
        if filename:
            self.load_file(filename)

    def shape_selection_changed(self, selected=False):
        if self._no_selection_slot:
            self._no_selection_slot = False
        else:
            shape = self.canvas.selected_shape
            if shape and shape in self.shapes_to_items:
                item = self.shapes_to_items[shape]
                self.bbox_list.blockSignals(True)
                self.bbox_list.setCurrentItem(item)
                self.bbox_list.blockSignals(False)
            else:
                self.bbox_list.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)

    def load_labels(self, shapes):
        s = []
        for label, points, line_color, fill_color, difficult in shapes:
            shape = Shape(label=label)
            for x, y in points:
                x, y, snapped = self.canvas.snap_point_to_canvas(x, y)
                if snapped:
                    self.set_dirty()
                shape.add_point(QPointF(x, y))
            shape.difficult = difficult
            shape.close()
            s.append(shape)
            shape.line_color = (QColor(*line_color) if line_color
                                else self.class_colors.get(label,
                                     generate_color_by_text(label)))
            shape.fill_color = (QColor(*fill_color) if fill_color
                                else self.class_colors.get(label,
                                     generate_color_by_text(label)))
            self.add_label(shape)
        self.canvas.load_shapes(s)

    def save_labels(self, annotation_file_path):
        annotation_file_path = ustr(annotation_file_path)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified

        def format_shape(s):
            return dict(
                label=s.label,
                line_color=s.line_color.getRgb(),
                fill_color=s.fill_color.getRgb(),
                points=[(p.x(), p.y()) for p in s.points],
                difficult=s.difficult,
            )

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                if not annotation_file_path.lower().endswith('.xml'):
                    annotation_file_path += XML_EXT
                self.label_file.save_pascal_voc_format(
                    annotation_file_path, shapes, self.file_path,
                    self.image_data, self.line_color.getRgb(),
                    self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO:
                if not annotation_file_path.lower().endswith('.txt'):
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_format(
                    annotation_file_path, shapes, self.file_path,
                    self.image_data, self.label_hist,
                    self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.CREATE_ML:
                if not annotation_file_path.lower().endswith('.json'):
                    annotation_file_path += JSON_EXT
                self.label_file.save_create_ml_format(
                    annotation_file_path, shapes, self.file_path,
                    self.image_data, self.label_hist,
                    self.line_color.getRgb(), self.fill_color.getRgb())
            else:
                self.label_file.save(
                    annotation_file_path, shapes, self.file_path,
                    self.image_data, self.line_color.getRgb(),
                    self.fill_color.getRgb())
            print(f'[Saved]  {os.path.basename(self.file_path)}  →  {os.path.basename(annotation_file_path)}')
            return True
        except LabelFileError as e:
            self.error_message('Error saving label data', f'<b>{e}</b>')
            return False

    def copy_shape_to_clipboard(self):
        """Ctrl+C — remember the selected shape for later paste."""
        if self.canvas.selected_shape:
            self._clipboard_shape = self.canvas.selected_shape

    def paste_shape_from_clipboard(self):
        """Ctrl+V — clone the clipboard shape onto the canvas."""
        if not self._clipboard_shape:
            return
        import copy as _copy
        new_shape = _copy.copy(self._clipboard_shape)
        offset = QPointF(10, 10)
        new_shape.points = [p + offset for p in new_shape.points]
        self.canvas.shapes.append(new_shape)
        self.canvas.selected_shape = new_shape
        self.add_label(new_shape)
        self.history.push(AddShapeCommand(self, new_shape), execute=False)
        self.shape_selection_changed(True)
        self.set_dirty()
        self.canvas.update()

    def copy_selected_shape(self):
        shape = self.canvas.copy_selected_shape()
        if shape:
            self.add_label(shape)
            self.history.push(AddShapeCommand(self, shape), execute=False)
            self.shape_selection_changed(True)
            self.set_dirty()

    def toggle_polygons(self, value):
        for i in range(self.bbox_list.count()):
            self.bbox_list.item(i).setCheckState(
                Qt.Checked if value else Qt.Unchecked)

    # ── new shape callback ────────────────────────────────────────────────────

    def new_shape(self):
        if self.single_class_mode.isChecked() and self.lastLabel:
            text = self.lastLabel
        else:
            text = self.label_dialog.pop_up(text=self.prev_label_text)
            self.lastLabel = text

        if text is not None:
            self.prev_label_text = text
            color = self.class_colors.get(text, generate_color_by_text(text))
            shape = self.canvas.set_last_label(text, color, color)
            self.add_label(shape)
            self.history.push(AddShapeCommand(self, shape), execute=False)
            if self.beginner():
                self.canvas.set_editing(True)
                self.actions.create.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
            self.set_dirty()
            if text not in self.label_hist:
                self.label_hist.append(text)
                self._ensure_class_in_table(text)
        else:
            self.canvas.reset_all_lines()

    # ── scroll / zoom ─────────────────────────────────────────────────────────

    def scroll_request(self, delta, orientation):
        units = -delta / (8 * 15)
        bar = self.scroll_bars[orientation]
        bar.setValue(int(bar.value() + bar.singleStep() * units))

    def set_zoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.MANUAL_ZOOM
        self.zoom_widget.setValue(int(value))

    def add_zoom(self, increment=10):
        self.set_zoom(self.zoom_widget.value() + increment)

    def zoom_request(self, delta):
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        pos    = QWidget.mapFromGlobal(self, QCursor.pos())
        w, h   = self.scroll_area.width(), self.scroll_area.height()
        margin = 0.1
        move_x = max(0, min((pos.x() - margin * w) / (w - 2 * margin * w), 1))
        move_y = max(0, min((pos.y() - margin * h) / (h - 2 * margin * h), 1))

        self.add_zoom(10 * delta / (8 * 15))

        h_bar.setValue(int(h_bar.value() + move_x * (h_bar.maximum() - h_bar_max)))
        v_bar.setValue(int(v_bar.value() + move_y * (v_bar.maximum() - v_bar_max)))

    def set_fit_window(self, value=True):
        if value: self.actions.fitWidth.setChecked(False)
        self.zoom_mode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_fit_width(self, value=True):
        if value: self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjust_scale()

    # ── file loading ──────────────────────────────────────────────────────────

    def load_file(self, file_path=None):
        self.reset_state()
        self.canvas.setEnabled(False)
        if file_path is None:
            file_path = self.settings.get(SETTING_FILENAME)

        file_path = ustr(file_path)
        unicode_file_path = os.path.abspath(file_path)

        if unicode_file_path and self.file_list_widget.count() > 0:
            if unicode_file_path in self.m_img_list:
                idx  = self.m_img_list.index(unicode_file_path)
                self.file_list_widget.item(idx).setSelected(True)
            else:
                self.file_list_widget.clear()
                self.m_img_list.clear()

        if unicode_file_path and os.path.exists(unicode_file_path):
            if LabelFile.is_label_file(unicode_file_path):
                try:
                    self.label_file = LabelFile(unicode_file_path)
                except LabelFileError as e:
                    self.error_message('Error opening file', f'<p><b>{e}</b></p>')
                    self.status(f'Error reading {unicode_file_path}')
                    return False
                self.image_data = self.label_file.image_data
                self.line_color = QColor(*self.label_file.lineColor)
                self.fill_color = QColor(*self.label_file.fillColor)
                self.canvas.verified = self.label_file.verified
            else:
                self.image_data  = read(unicode_file_path, None)
                self.label_file  = None
                self.canvas.verified = unicode_file_path in self.verified_images

            if isinstance(self.image_data, QImage):
                image = self.image_data
            else:
                image = QImage.fromData(self.image_data)

            if image.isNull():
                self.error_message('Error opening file',
                                   f'<p>Cannot load <i>{unicode_file_path}</i></p>')
                self.status(f'Error reading {unicode_file_path}')
                return False

            self.status(f'Loaded {os.path.basename(unicode_file_path)}')
            self.image     = image
            self.file_path = unicode_file_path
            self.canvas.load_pixmap(QPixmap.fromImage(image))
            if self.label_file:
                self.load_labels(self.label_file.shapes)
            self.set_clean()
            self.canvas.setEnabled(True)
            self.adjust_scale(initial=True)
            self.paint_canvas()
            self.add_recent_file(self.file_path)
            self.toggle_actions(True)
            self.show_bounding_box_from_annotation_file(file_path)
            self._update_file_verify_icon(unicode_file_path)

            counter = self.counter_str()
            self.setWindowTitle(f'{__appname__} {file_path} {counter}')

            if self.bbox_list.count():
                last = self.bbox_list.item(self.bbox_list.count() - 1)
                self.bbox_list.setCurrentItem(last)
                last.setSelected(True)

            self.canvas.setFocus(True)
            return True
        return False

    def counter_str(self):
        return f'[{self.cur_img_idx + 1} / {self.img_count}]'

    def show_bounding_box_from_annotation_file(self, file_path):
        if self.default_save_dir is not None:
            annotation_dir = self.default_save_dir
            base      = os.path.basename(os.path.splitext(file_path)[0])
            xml_path  = os.path.join(annotation_dir, base + XML_EXT)
            txt_path  = os.path.join(annotation_dir, base + TXT_EXT)
            json_path = os.path.join(annotation_dir, base + JSON_EXT)
        else:
            annotation_dir = os.path.dirname(file_path)
            xml_path  = os.path.splitext(file_path)[0] + XML_EXT
            txt_path  = os.path.splitext(file_path)[0] + TXT_EXT
            json_path = os.path.splitext(file_path)[0] + JSON_EXT

        # Sync class table from classes.txt in the annotation directory
        self._load_classes_txt(annotation_dir)

        if   os.path.isfile(xml_path):  self.load_pascal_xml_by_filename(xml_path)
        elif os.path.isfile(txt_path):  self.load_yolo_txt_by_filename(txt_path)
        elif os.path.isfile(json_path): self.load_create_ml_json_by_filename(json_path, file_path)

        self._update_class_counts()

    def resizeEvent(self, event):
        if (self.canvas and not self.image.isNull()
                and self.zoom_mode != self.MANUAL_ZOOM):
            self.adjust_scale()
        super().resizeEvent(event)

    def paint_canvas(self):
        assert not self.image.isNull(), 'cannot paint null image'
        self.canvas.scale = 0.01 * self.zoom_widget.value()
        self.canvas.label_font_size = int(
            0.02 * max(self.image.width(), self.image.height()))
        self.canvas.adjustSize()
        self.canvas.update()

    def adjust_scale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoom_mode]()
        self.zoom_widget.setValue(int(100 * value))

    def scale_fit_window(self):
        e  = 2.0
        w1 = self.centralWidget().width()  - e
        h1 = self.centralWidget().height() - e
        w2 = self.canvas.pixmap.width()  - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        return w1 / w2 if (w2 / h2) >= (w1 / h1) else h1 / h2

    def scale_fit_width(self):
        return (self.centralWidget().width() - 2.0) / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.may_continue():
            event.ignore()
            return
        settings = self.settings
        settings[SETTING_FILENAME]    = (self.file_path or '') if self.dir_name is None else ''
        settings[SETTING_WIN_SIZE]    = self.size()
        settings[SETTING_WIN_POSE]    = self.pos()
        settings[SETTING_WIN_STATE]   = self.saveState()
        settings[SETTING_LINE_COLOR]  = self.line_color
        settings[SETTING_FILL_COLOR]  = self.fill_color
        settings[SETTING_RECENT_FILES] = self.recent_files
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        settings[SETTING_SAVE_DIR]    = (ustr(self.default_save_dir)
                                         if self.default_save_dir
                                         and os.path.exists(self.default_save_dir)
                                         else '')
        settings[SETTING_LAST_OPEN_DIR] = (self.last_open_dir
                                           if self.last_open_dir
                                           and os.path.exists(self.last_open_dir)
                                           else '')
        settings[SETTING_AUTO_SAVE]         = self.auto_saving.isChecked()
        settings[SETTING_SINGLE_CLASS]      = self.single_class_mode.isChecked()
        settings[SETTING_PAINT_LABEL]       = self.display_label_option.isChecked()
        settings[SETTING_DRAW_SQUARE]       = self.draw_squares_option.isChecked()
        settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format
        settings.save()

    def load_recent(self, filename):
        if self.may_continue():
            self.load_file(filename)

    def scan_all_images(self, folder_path):
        extensions = [
            f'.{fmt.data().decode("ascii").lower()}'
            for fmt in QImageReader.supportedImageFormats()
        ]
        images = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    images.append(ustr(os.path.abspath(
                        os.path.join(root, file))))
        natural_sort(images, key=lambda x: x.lower())
        return images

    def change_save_dir_dialog(self, _value=False):
        path = ustr(self.default_save_dir) if self.default_save_dir else '.'
        dir_path = ustr(QFileDialog.getExistingDirectory(
            self, f'{__appname__} - Save annotations to directory', path,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        if dir_path and len(dir_path) > 1:
            self.default_save_dir = dir_path
            self._load_classes_txt(dir_path)
        self.statusBar().showMessage(
            f'Annotations will be saved to {self.default_save_dir}')
        self.statusBar().show()

    def open_annotation_dialog(self, _value=False):
        if self.file_path is None:
            self.statusBar().showMessage('Please select an image first')
            return
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            filename = ustr(QFileDialog.getOpenFileName(
                self, f'{__appname__} - Choose XML file', path,
                'Open Annotation XML file (*.xml)'))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
                self.load_pascal_xml_by_filename(filename)

    def open_dir_dialog(self, _value=False, dir_path=None, silent=False):
        if not self.may_continue():
            return
        default = dir_path if dir_path else '.'
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            default = self.last_open_dir
        elif self.file_path:
            default = os.path.dirname(self.file_path)
        if not silent:
            target = ustr(QFileDialog.getExistingDirectory(
                self, f'{__appname__} - Open Directory', default,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        else:
            target = ustr(default)
        self.last_open_dir = target
        self.import_dir_images(target)

    def import_dir_images(self, dir_path):
        if not self.may_continue() or not dir_path:
            return
        self.last_open_dir = dir_path
        self.dir_name      = dir_path
        self.file_path     = None
        self.file_list_widget.clear()
        self.m_img_list = self.scan_all_images(dir_path)
        self.img_count  = len(self.m_img_list)
        self.open_next_image()
        for imgPath in self.m_img_list:
            item = QListWidgetItem(imgPath)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if imgPath in self.verified_images
                               else Qt.Unchecked)
            self.file_list_widget.addItem(item)

    def open_prev_image(self, _value=False):
        if self.auto_saving.isChecked():
            if self.default_save_dir:
                if self.dirty: self.save_file()
            else:
                self.change_save_dir_dialog()
                return
        if not self.may_continue() or self.img_count <= 0 or self.file_path is None:
            return
        if self.cur_img_idx - 1 >= 0:
            self.cur_img_idx -= 1
            filename = self.m_img_list[self.cur_img_idx]
            if filename:
                self.load_file(filename)

    def open_next_image(self, _value=False):
        if self.auto_saving.isChecked():
            if self.default_save_dir:
                if self.dirty: self.save_file()
            else:
                self.change_save_dir_dialog()
                return
        if not self.may_continue() or self.img_count <= 0:
            return
        filename = None
        if self.file_path is None:
            filename = self.m_img_list[0]
            self.cur_img_idx = 0
        elif self.cur_img_idx + 1 < self.img_count:
            self.cur_img_idx += 1
            filename = self.m_img_list[self.cur_img_idx]
        if filename:
            self.load_file(filename)

    def open_file(self, _value=False):
        if not self.may_continue():
            return
        path    = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        formats = [f'*.{fmt.data().decode("ascii").lower()}'
                   for fmt in QImageReader.supportedImageFormats()]
        filters = (f'Image & Label files '
                   f'({" ".join(formats + ["*" + LabelFile.suffix])})')
        filename = QFileDialog.getOpenFileName(
            self, f'{__appname__} - Choose Image or Label file', path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.cur_img_idx = 0
            self.img_count   = 1
            self.load_file(filename)

    def save_file(self, _value=False):
        if self.default_save_dir and len(ustr(self.default_save_dir)):
            if self.file_path:
                saved_path = os.path.join(
                    ustr(self.default_save_dir),
                    os.path.splitext(os.path.basename(self.file_path))[0])
                self._save_file(saved_path)
        else:
            image_dir  = os.path.dirname(self.file_path)
            saved_path = os.path.join(
                image_dir,
                os.path.splitext(os.path.basename(self.file_path))[0])
            self._save_file(saved_path if self.label_file
                            else self.save_file_dialog(remove_ext=False))

    def save_file_as(self, _value=False):
        assert not self.image.isNull(), 'cannot save empty image'
        self._save_file(self.save_file_dialog())

    def save_file_dialog(self, remove_ext=True):
        caption = f'{__appname__} - Choose File'
        dlg     = QFileDialog(self, caption, self.current_path(),
                              f'File (*{LabelFile.suffix})')
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        dlg.selectFile(os.path.splitext(self.file_path)[0])
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            full = ustr(dlg.selectedFiles()[0])
            return os.path.splitext(full)[0] if remove_ext else full
        return ''

    def _save_file(self, annotation_file_path):
        if annotation_file_path and self.save_labels(annotation_file_path):
            self.set_clean()
            self.statusBar().showMessage(f'Saved to {annotation_file_path}')
            self.statusBar().show()

    def close_file(self, _value=False):
        if not self.may_continue():
            return
        self.reset_state()
        self.set_clean()
        self.toggle_actions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def delete_image(self):
        delete_path = self.file_path
        if delete_path is not None:
            self.open_next_image()
            self.cur_img_idx -= 1
            self.img_count   -= 1
            if os.path.exists(delete_path):
                os.remove(delete_path)
            self.import_dir_images(self.last_open_dir)

    def reset_all(self):
        self.settings.reset()
        self.close()
        QProcess().startDetached(sys.executable, [os.path.abspath(__file__)])

    def may_continue(self):
        if not self.dirty:
            return True
        result = QMessageBox.warning(
            self, 'Attention',
            'You have unsaved changes, save them?\n'
            'Click "No" to discard all changes.',
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        if result == QMessageBox.No:    return True
        if result == QMessageBox.Yes:   self.save_file(); return True
        return False

    def discard_changes_dialog(self):
        return QMessageBox.warning(
            self, 'Attention',
            'You have unsaved changes, save them?\n'
            'Click "No" to discard all changes.',
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)

    def error_message(self, title, message):
        return QMessageBox.critical(
            self, title, f'<p><b>{title}</b></p>{message}')

    def current_path(self):
        return os.path.dirname(self.file_path) if self.file_path else '.'

    def choose_color1(self):
        color = self.color_dialog.getColor(
            self.line_color, 'Choose line color', default=DEFAULT_LINE_COLOR)
        if color:
            self.line_color = color
            Shape.line_color = color
            self.canvas.set_drawing_color(color)
            self.canvas.update()
            self.set_dirty()

    def delete_selected_shape(self, *_args):
        shape = self.canvas.selected_shape
        if shape:
            cmd = DeleteShapeCommand(self, shape)
            self.history.push(cmd)
            if self.no_shapes():
                for act in self.actions.onShapesPresent:
                    act.setEnabled(False)

    def choose_shape_line_color(self):
        color = self.color_dialog.getColor(
            self.line_color, 'Choose Line Color', default=DEFAULT_LINE_COLOR)
        if color and self.canvas.selected_shape:
            self.canvas.selected_shape.line_color = color
            self.canvas.update()
            self.set_dirty()

    def choose_shape_fill_color(self):
        color = self.color_dialog.getColor(
            self.fill_color, 'Choose Fill Color', default=DEFAULT_FILL_COLOR)
        if color and self.canvas.selected_shape:
            self.canvas.selected_shape.fill_color = color
            self.canvas.update()
            self.set_dirty()

    def load_predefined_classes(self, predef_classes_file):
        if predef_classes_file and os.path.exists(predef_classes_file):
            with codecs.open(predef_classes_file, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.label_hist.append(line)

    def load_pascal_xml_by_filename(self, xml_path):
        if self.file_path is None or not os.path.isfile(xml_path):
            return
        self.set_format(FORMAT_PASCALVOC)
        reader = PascalVocReader(xml_path)
        self.load_labels(reader.get_shapes())
        self.canvas.verified = reader.verified

    def load_yolo_txt_by_filename(self, txt_path):
        if self.file_path is None or not os.path.isfile(txt_path):
            return
        self.set_format(FORMAT_YOLO)
        reader = YoloReader(txt_path, self.image, self.label_hist)
        shapes = reader.get_shapes()
        print(f'[Loaded] {len(shapes)} box(es)  —  {os.path.basename(self.file_path)}')
        self.load_labels(shapes)
        self.canvas.verified = reader.verified

    def load_create_ml_json_by_filename(self, json_path, file_path):
        if self.file_path is None or not os.path.isfile(json_path):
            return
        self.set_format(FORMAT_CREATEML)
        reader = CreateMLReader(json_path, file_path)
        self.load_labels(reader.get_shapes())
        self.canvas.verified = reader.verified

    def copy_previous_bounding_boxes(self):
        if self.file_path not in self.m_img_list:
            return
        idx = self.m_img_list.index(self.file_path)
        if idx - 1 >= 0:
            self.show_bounding_box_from_annotation_file(self.m_img_list[idx - 1])
            self.save_file()

    def toggle_paint_labels_option(self):
        for shape in self.canvas.shapes:
            shape.paint_label = self.display_label_option.isChecked()
        self.canvas.update()

    def toggle_draw_square(self):
        self.canvas.set_drawing_shape_to_square(
            self.draw_squares_option.isChecked())


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def inverted(color):
    return QColor(*[255 - v for v in color.getRgb()])


def read(filename, default=None):
    try:
        reader = QImageReader(filename)
        reader.setAutoTransform(True)
        img = reader.read()
        return img if not img.isNull() else default
    except Exception:
        return default


# ══════════════════════════════════════════════════════════════════════════════
# Entry points
# ══════════════════════════════════════════════════════════════════════════════

def get_main_app(argv=None):
    if argv is None:
        argv = []
    app = QApplication(argv)
    app.setApplicationName(__appname__)
    app.setWindowIcon(new_icon('app'))

    argparser = argparse.ArgumentParser()
    argparser.add_argument('image_dir', nargs='?')
    argparser.add_argument(
        'class_file',
        default=os.path.join(os.path.dirname(__file__),
                             'data', 'predefined_classes.txt'),
        nargs='?')
    argparser.add_argument('save_dir', nargs='?')
    args = argparser.parse_args(argv[1:])

    args.image_dir  = args.image_dir  and os.path.normpath(args.image_dir)
    args.class_file = args.class_file and os.path.normpath(args.class_file)
    args.save_dir   = args.save_dir   and os.path.normpath(args.save_dir)

    win = MainWindow(args.image_dir, args.class_file, args.save_dir)
    win.show()
    return app, win


def main():
    app, _win = get_main_app(sys.argv)
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
