from PyQt5.QtWidgets import QListWidgetItem


class HashableQListWidgetItem(QListWidgetItem):
    """QListWidgetItem that can be used as a dictionary key."""

    def __init__(self, *args):
        super().__init__(*args)

    def __hash__(self):
        return id(self)
