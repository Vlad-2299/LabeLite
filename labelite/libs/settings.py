from PyQt5.QtCore import QSettings


class Settings:
    """Thin wrapper around QSettings for typed get/set."""

    def __init__(self):
        self._settings = QSettings('labelImg', 'labelImg')

    def load(self):
        pass  # QSettings loads lazily

    def save(self):
        self._settings.sync()

    def reset(self):
        self._settings.clear()
        self._settings.sync()

    def get(self, key, default=None):
        if default is not None and not isinstance(default, type):
            # Use the default's type as a hint so QSettings returns the right Python type
            value = self._settings.value(key, default, type(default))
        else:
            value = self._settings.value(key)
            if value is None:
                return default
        return value

    def __setitem__(self, key, value):
        self._settings.setValue(key, value)

    def __getitem__(self, key):
        return self._settings.value(key)

    def __contains__(self, key):
        return self._settings.contains(key)
