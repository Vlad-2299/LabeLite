from PyQt5.QtWidgets import QSpinBox


class ZoomWidget(QSpinBox):
    def __init__(self, value=100):
        super().__init__()
        self.setButtonSymbols(QSpinBox.NoButtons)
        self.setRange(1, 500)
        self.setSuffix(' %')
        self.setValue(value)
        self.setToolTip('Zoom level')
        self.setStatusTip(self.toolTip())
        self.setAlignment(__import__('PyQt5.QtCore', fromlist=['Qt']).Qt.AlignCenter)

    def minimumSizeHint(self):
        height = super().minimumSizeHint().height()
        fm = self.fontMetrics()
        width = fm.boundingRect(str(self.maximum())).width() + 30
        return __import__('PyQt5.QtCore', fromlist=['QSize']).QSize(width, height)
