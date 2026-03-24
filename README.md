# labelite

A debloated, modernised image annotation tool for producing **YOLO bounding-box labels**.
Rewritten for Python 3.10+ / PyQt5 — no Qt resource compiler, no legacy PyQt4 fallback, no `distutils`.

> **Based on [labelImg](https://github.com/tzutalin/labelImg) by [Tzutalin](https://github.com/tzutalin)**, licensed under MIT.
> The original project provided the UI concept, format readers/writers, and overall architecture.
> This fork strips the codebase to its essentials, modernises it for Python 3.10+ / PyQt5 5.15,
> and redesigns the annotation workflow.

---

## Requirements

[uv](https://docs.astral.sh/uv/)

Install uv if you don't have it:

```bash
# Windows
winget install astral-sh.uv

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Install & Run

```bash
git clone https://github.com/Vlad-2299/labelite
cd labelite
uv venv
.venv\Scripts\activate / source .venv/bin/activate
uv pip install -e .
labelite / python -m labelite.labelite
```

---

## Workflow

### 1. Open images

Use **File → Open Dir** to load a folder of images.
The file list on the right shows every image found. Supported formats are whatever your Qt installation can decode (JPEG, PNG, BMP, TIFF, etc.).

### 2. Set an annotation directory (optional)

**File → Change Save Dir** points annotation files to a folder separate from the images.
If you skip this step, annotation files are saved alongside the images.

### 3. Define classes

Place a `classes.txt` file in the annotation directory (or image directory):

```
cat
dog
bird
```

Line number = class ID (0-indexed). The **Classes** panel on the right populates automatically when the first annotation file is read.
Each class gets a colour swatch — click to change it.

### 4. Annotate

| Action | How |
|---|---|
| Enter draw mode | Press **W** or click the **Create Box** toolbar button |
| Draw a box | Click-drag, release |
| Constrain to square | Hold **Ctrl** while drawing |
| Cancel draw | Press **Esc** |
| Select a box | Click it |
| Move a box | Click-drag the selected box |
| Resize a box | Drag any of the 8 handles on the selected box |
| Delete a box | Select it, press **Delete** |
| Copy a box | Select it, press **Ctrl+C** |
| Paste the copy | Press **Ctrl+V** (places a 10 px offset clone) |
| Change box class | Double-click it in the **Bounding Boxes** list, or right-click → **Change Label** |
| Hide/show a box | Toggle the checkbox next to it in the **Bounding Boxes** list |

### 5. Navigate images

| Action | Key / Button |
|---|---|
| Previous image | **A** or toolbar **Prev** button |
| Next image | **D** or toolbar **Next** button |
| Double-click in file list | Jump to any image |

### 6. Save

**Ctrl+S** saves the annotation for the current image.
The default format is **YOLO**. Cycle through formats with the format button on the toolbar (`YOLO` → `PascalVOC` → `CreateML`).

YOLO save produces two files next to (or in the annotation dir for) each image:

```
image_name.txt       ← one line per box: <class_id> <cx> <cy> <w> <h>
classes.txt          ← written/updated with the current class list
```

### 7. Verify images

Press **Space** to toggle a checkmark on the current file in the file list.
This is a visual marker only — no file is written.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `W` | Create box |
| `A` | Previous image |
| `D` | Next image |
| `Delete` | Delete selected box |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+C` | Copy selected box |
| `Ctrl+V` | Paste box |
| `Ctrl+D` | Duplicate selected box (immediate offset copy) |
| `Ctrl+E` | Change label of selected box |
| `Ctrl+H` | Hide all boxes |
| `Ctrl+A` | Show all boxes |
| `Ctrl+F` | Fit image to window |
| `Ctrl++` / `Ctrl+-` | Zoom in / out |
| `Space` | Toggle verify mark on current image |
| `Esc` | Cancel drawing |
| Middle-mouse drag | Pan the canvas |
| `Ctrl` + scroll | Zoom |
| Scroll | Pan vertically |
| `Shift` + scroll | Pan horizontally |

---

## Project layout

```
labelite/
├── pyproject.toml
├── README.md
└── labelite/
    ├── labelite.py          # Main window, command pattern, all UI logic
    ├── data/
    │   └── classes.txt
    │   └── image1.txt
    │   └── image1.png
    └── libs/
        ├── canvas.py        # Drawing, selection, move/resize of bounding boxes
        ├── shape.py         # Shape data model and painter
        ├── yolo_io.py       # YOLO TXT reader / writer
        ├── pascal_voc_io.py # Pascal VOC XML reader / writer
        ├── create_ml_io.py  # CreateML JSON reader / writer
        ├── labelFile.py     # Format dispatcher
        ├── labelDialog.py   # Label-picker dialog
        ├── colorDialog.py   # Colour picker wrapper
        ├── settings.py      # QSettings persistence
        ├── stringBundle.py  # UI strings
        └── utils.py         # Icons, actions, class colours
```

---

## Annotation format reference

### YOLO (default)

```
<class_id> <x_center> <y_center> <width> <height>
```

All values normalised to `[0, 1]` relative to image dimensions.
`classes.txt` in the same directory maps line index → class name.

### Pascal VOC

Standard `<annotation>` XML. Pixel coordinates, absolute.

### CreateML

JSON array of `{ "image": "...", "annotations": [...] }` objects.

---

## Tips

- **Batch a dataset**: open the image directory, set a save directory, use **D** to step through images and **Ctrl+S** to save each one. Enable **Auto Save** in the View menu to save automatically on image change.
- **Single-class datasets**: enable **View → Single Class Mode** — the label dialog is skipped after the first box and the same class is reused.
- **classes.txt is the source of truth**: edit it directly to rename or reorder classes, then reopen the folder. The class panel refreshes from it on every file load.

---

## Credits

labelite is a fork of **[labelImg](https://github.com/tzutalin/labelImg)**
by **[Tzutalin](https://github.com/tzutalin)**, used under the
[MIT License](https://github.com/tzutalin/labelImg/blob/master/LICENSE).
