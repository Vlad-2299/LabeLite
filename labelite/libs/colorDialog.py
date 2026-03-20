from PyQt5.QtWidgets import QColorDialog
from PyQt5.QtGui import QColor


class ColorDialog(QColorDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOption(QColorDialog.ShowAlphaChannel)

    def getColor(self, value=None, title='', default=None):
        self.setCurrentColor(value or default or QColor())
        self.setWindowTitle(title)
        if self.exec_():
            return self.currentColor()
        return None
