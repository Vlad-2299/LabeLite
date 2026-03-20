from PyQt5.QtWidgets import QWidget, QHBoxLayout, QComboBox


class ComboBox(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.cb = QComboBox()
        layout.addWidget(self.cb)
        self.setLayout(layout)
        self.cb.currentIndexChanged.connect(self._on_index_changed)

    def _on_index_changed(self, index):
        # Bubble up to parent if it has combo_selection_changed
        parent = self.parent()
        if parent and hasattr(parent, 'combo_selection_changed'):
            parent.combo_selection_changed(index)

    def update_items(self, items):
        self.cb.clear()
        for item in items:
            self.cb.addItem(item)
