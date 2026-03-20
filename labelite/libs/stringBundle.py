_STRINGS = {
    # Menus
    'menu_file':   'File',
    'menu_edit':   'Edit',
    'menu_view':   'View',
    'menu_help':   'Help',
    'menu_openRecent': 'Open Recent',

    # File actions
    'quit':        'Quit',
    'quitApp':     'Quit application',
    'openFile':    'Open File',
    'openFileDetail': 'Open image or label file',
    'openDir':     'Open Directory',
    'changeSaveDir': 'Change Save Dir',
    'changeSavedAnnotationDir': 'Change the directory to save annotations',
    'openAnnotation': 'Open Annotation',
    'openAnnotationDetail': 'Open annotation file',
    'copyPrevBounding': 'Copy Previous Bounding Boxes',
    'nextImg':     'Next Image',
    'nextImgDetail': 'Open next image (D)',
    'prevImg':     'Prev Image',
    'prevImgDetail': 'Open previous image (A)',
    'verifyImg':   'Verify Image',
    'verifyImgDetail': 'Mark image as verified',
    'save':        'Save',
    'saveDetail':  'Save labels to file',
    'changeSaveFormat': 'Cycle save format (VOC / YOLO / CreateML)',
    'saveAs':      'Save As',
    'saveAsDetail': 'Save labels to a different file',
    'closeCur':    'Close',
    'closeCurDetail': 'Close current file',
    'deleteImg':   'Delete Image',
    'deleteImgDetail': 'Delete the current image file',
    'resetAll':    'Reset All',
    'resetAllDetail': 'Reset all settings',

    # Edit actions
    'editLabel':   'Edit Label',
    'editLabelDetail': 'Edit the label of the selected box',
    'crtBox':      'Create Box',
    'crtBoxDetail': 'Draw a new bounding box (W)',
    'editBox':     'Edit Box',
    'editBoxDetail': 'Switch to edit/select mode',
    'delBox':      'Delete Box',
    'delBoxDetail': 'Delete the selected bounding box',
    'dupBox':      'Duplicate Box',
    'dupBoxDetail': 'Duplicate the selected bounding box',
    'copyPrevBounding': 'Copy Prev Boxes',

    # View actions
    'advancedMode': 'Advanced Mode',
    'advancedModeDetail': 'Switch to advanced mode',
    'hideAllBox':  'Hide All Boxes',
    'hideAllBoxDetail': 'Hide all bounding boxes',
    'showAllBox':  'Show All Boxes',
    'showAllBoxDetail': 'Show all bounding boxes',
    'autoSaveMode': 'Auto Save',
    'singleClsMode': 'Single Class Mode',
    'displayLabel': 'Display Label',
    'drawSquares': 'Draw Squares',

    # Zoom
    'zoomin':      'Zoom In',
    'zoominDetail': 'Zoom in (Ctrl++)',
    'zoomout':     'Zoom Out',
    'zoomoutDetail': 'Zoom out (Ctrl+-)',
    'originalsize': 'Original Size',
    'originalsizeDetail': 'Zoom to original size',
    'fitWin':      'Fit Window',
    'fitWinDetail': 'Fit image to window',
    'fitWidth':    'Fit Width',
    'fitWidthDetail': 'Fit image width to window',

    # Colors
    'boxLineColor': 'Box Line Color',
    'boxLineColorDetail': 'Choose the line color for new boxes',
    'shapeLineColor': 'Shape Line Color',
    'shapeLineColorDetail': 'Choose the line color for this shape',
    'shapeFillColor': 'Shape Fill Color',
    'shapeFillColorDetail': 'Choose the fill color for this shape',

    # Help
    'tutorialDefault': 'Tutorial',
    'tutorialDetail': 'Open labelImg tutorial',
    'info':        'Info',
    'shortcut':    'Shortcuts',

    # Dock widgets
    'boxLabelText': 'Box Labels',
    'labels':      'labels',
    'fileList':    'File List',
    'files':       'files',
    'showHide':    'Show/Hide Label Panel',

    # Misc
    'useDefaultLabel': 'Use Default Label',
    'useDifficult': 'Difficult',

    # Undo/Redo
    'undo':        'Undo',
    'undoDetail':  'Undo last action (Ctrl+Z)',
    'redo':        'Redo',
    'redoDetail':  'Redo last undone action (Ctrl+Y)',
}


class StringBundle:
    _instance = None

    @classmethod
    def get_bundle(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_string(self, str_id):
        return _STRINGS.get(str_id, str_id)
