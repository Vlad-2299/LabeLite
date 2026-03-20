from PyQt5.QtWidgets import QToolBar, QSizePolicy
from PyQt5.QtCore import Qt


class ToolBar(QToolBar):
    def __init__(self, title):
        super().__init__(title)
        layout = self.layout()
        m = (0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setContentsMargins(*m)
        self.setContentsMargins(*m)
        self.setWindowTitle(title)

    def addAction(self, action):
        if isinstance(action, QToolBar):
            self.addWidget(action)
        else:
            super().addAction(action)
            btn = self.widgetForAction(action)
            if btn:
                btn.setFixedSize(36, 36)
