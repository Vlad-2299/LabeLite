from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout,
                             QListWidget, QLineEdit, QListWidgetItem)
from PyQt5.QtCore import Qt


class LabelDialog(QDialog):
    def __init__(self, text='Enter label', parent=None, list_item=None):
        super().__init__(parent)
        self.setWindowTitle('Label')
        self.edit = QLineEdit(text)
        self.edit.setPlaceholderText('Type or select a label…')

        layout = QVBoxLayout()
        layout.addWidget(self.edit)

        self.list_widget = QListWidget()
        if list_item:
            for item in list_item:
                self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(self._on_double_click)
        self.list_widget.itemClicked.connect(self._on_click)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self.edit.setFocus()

    def _on_click(self, item):
        self.edit.setText(item.text())

    def _on_double_click(self, item):
        self.edit.setText(item.text())
        self.accept()

    def pop_up(self, text='', move=True):
        """Show dialog pre-filled with *text*.  Returns the entered string or None."""
        self.edit.setText(text)
        self.edit.setSelection(0, len(text))

        # Sync list with current label history on parent
        parent = self.parent()
        if parent and hasattr(parent, 'label_hist'):
            self.list_widget.clear()
            for item in parent.label_hist:
                self.list_widget.addItem(item)
                # Pre-select if matches
                if item == text:
                    row = self.list_widget.count() - 1
                    self.list_widget.setCurrentRow(row)

        if self.exec_():
            return self.edit.text().strip() or None
        return None
