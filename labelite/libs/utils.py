"""Misc UI utilities."""
import hashlib
import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter, QFont
from PyQt5.QtWidgets import QAction, QMenu, QApplication


# ─── class-aware colour map ──────────────────────────────────────────────────
# These colours are used for the two tick classes.  Any other label falls back
# to a hash-derived colour so the tool still works on arbitrary datasets.
CLASS_COLORS = {
    'fed':   QColor(220,  55,  55, 200),   # Red
    'unfed': QColor( 55, 120, 220, 200),   # Blue
}


def generate_color_by_text(text):
    """Return a deterministic QColor for a label string."""
    key = text.lower().strip()
    if key in CLASS_COLORS:
        return QColor(CLASS_COLORS[key])          # copy so callers can mutate alpha
    digest = hashlib.md5(text.encode('utf-8')).digest()
    r, g, b = digest[0], digest[1], digest[2]
    # Keep colours reasonably saturated / visible
    return QColor(max(r, 60), max(g, 60), max(b, 60), 200)


# ─── simple namespace ────────────────────────────────────────────────────────
class Struct:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


# ─── icons ───────────────────────────────────────────────────────────────────
_QT_ICON_MAP = {
    'open':      QApplication.style if False else None,   # resolved lazily below
}

# Map icon names → (short label, hex background colour)
_TEXT_ICONS = {
    'open':         ('📂', '#3498db'),
    'save':         ('💾', '#27ae60'),
    'save-as':      ('S↗', '#2980b9'),
    'close':        ('✕',  '#c0392b'),
    'quit':         ('⏻',  '#7f8c8d'),
    'new':          ('+',  '#2ecc71'),
    'delete':       ('🗑', '#e74c3c'),
    'copy':         ('⧉',  '#9b59b6'),
    'edit':         ('✎',  '#2980b9'),
    'next':         ('▶',  '#3498db'),
    'prev':         ('◀',  '#3498db'),
    'zoom-in':      ('+🔍', '#16a085'),
    'zoom-out':     ('-🔍', '#16a085'),
    'zoom':         ('🔍', '#16a085'),
    'fit-window':   ('⊡',  '#8e44ad'),
    'fit-width':    ('⟺',  '#8e44ad'),
    'verify':       ('✔',  '#27ae60'),
    'help':         ('?',  '#2980b9'),
    'resetall':     ('↺',  '#e67e22'),
    'labels':       ('☰',  '#34495e'),
    'expert':       ('★',  '#c0392b'),
    'hide':         ('👁', '#95a5a6'),
    'color':        ('🎨', '#e67e22'),
    'color_line':   ('─',  '#1abc9c'),
    'format_voc':   ('VOC', '#2ecc71'),
    'format_yolo':  ('YL',  '#e67e22'),
    'format_createml': ('ML', '#9b59b6'),
    'undo':         ('↩',  '#16a085'),
    'redo':         ('↪',  '#d35400'),
    'app':          ('🎯', '#2c3e50'),
}


def _make_icon(label, bg_hex):
    pix = QPixmap(28, 28)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(bg_hex))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(1, 1, 26, 26, 5, 5)
    p.setPen(QColor('white'))
    font = QFont()
    font.setPixelSize(11)
    font.setBold(True)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignCenter, label)
    p.end()
    return QIcon(pix)


_icon_cache = {}


def new_icon(name):
    if name not in _icon_cache:
        label, bg = _TEXT_ICONS.get(name, ('?', '#7f8c8d'))
        _icon_cache[name] = _make_icon(label, bg)
    return _icon_cache[name]


# ─── action helper ───────────────────────────────────────────────────────────
def new_action(parent, text, slot=None, shortcut=None, icon=None,
               tip=None, checkable=False, enabled=True):
    a = QAction(text, parent)
    if icon is not None:
        a.setIcon(new_icon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            a.setShortcuts(shortcut)
        else:
            a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    a.setCheckable(checkable)
    a.setEnabled(enabled)
    return a


def add_actions(widget, actions):
    for action in actions:
        if action is None:
            widget.addSeparator()
        elif isinstance(action, QMenu):
            widget.addMenu(action)
        else:
            widget.addAction(action)


# ─── misc ────────────────────────────────────────────────────────────────────
def have_qstring():
    """Always False in PyQt5 (QString does not exist)."""
    return False


def format_shortcut(text):
    return text


def natural_sort(lst, key=lambda x: x):
    def _convert(s):
        return int(s) if s.isdigit() else s.lower()

    def _key(item):
        return [_convert(c) for c in re.split(r'(\d+)', key(item))]

    lst.sort(key=_key)
