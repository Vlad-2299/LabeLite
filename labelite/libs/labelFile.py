"""LabelFile – orchestrates save/load across formats."""
import os

from PyQt5.QtGui import QImage

from libs.pascal_voc_io import PascalVocWriter, XML_EXT
from libs.yolo_io       import YoloWriter,      TXT_EXT
from libs.create_ml_io  import CreateMLWriter,   JSON_EXT
from libs.ustr          import ustr


class LabelFileError(Exception):
    pass


class LabelFileFormat:
    PASCAL_VOC = 0
    YOLO       = 1
    CREATE_ML  = 2


class LabelFile:
    suffix = XML_EXT   # default, updated dynamically

    def __init__(self, filename=None):
        self.shapes    = []
        self.image_data = None
        self.verified  = False
        self.lineColor = (0, 255, 0, 255)
        self.fillColor = (0, 255, 0, 128)
        # We don't load a native format: images are always loaded raw.

    @staticmethod
    def is_label_file(filename):
        """We never use a proprietary format; always return False."""
        return False

    def toggle_verify(self):
        self.verified = not self.verified

    # ── Pascal VOC ────────────────────────────────────────────────────────────
    def save_pascal_voc_format(self, annotation_path, shapes, image_path,
                               image_data, line_color, fill_color):
        img = QImage()
        if isinstance(image_data, QImage):
            img = image_data
        elif image_data:
            img.loadFromData(image_data)

        img_size = (img.height(), img.width(), 3)
        folder   = os.path.basename(os.path.dirname(image_path))
        filename = os.path.basename(image_path)
        writer   = PascalVocWriter(folder, filename, img_size)
        writer.verified = self.verified

        for shape in shapes:
            pts   = shape['points']
            xs    = [p[0] for p in pts]
            ys    = [p[1] for p in pts]
            writer.add_bnd_box(min(xs), min(ys), max(xs), max(ys),
                               shape['label'], shape.get('difficult', False))

        writer.save(annotation_path)

    # ── YOLO ─────────────────────────────────────────────────────────────────
    def save_yolo_format(self, annotation_path, shapes, image_path,
                         image_data, label_hist, line_color, fill_color):
        img = QImage()
        if isinstance(image_data, QImage):
            img = image_data
        elif image_data:
            img.loadFromData(image_data)

        img_size = (img.height(), img.width())
        folder   = os.path.basename(os.path.dirname(image_path))
        filename = os.path.basename(image_path)
        writer   = YoloWriter(folder, filename, img_size)
        writer.verified = self.verified

        # Use a mutable copy so YoloWriter can append unknown classes
        class_list = list(label_hist)

        for shape in shapes:
            pts = shape['points']
            xs  = [p[0] for p in pts]
            ys  = [p[1] for p in pts]
            writer.add_bnd_box(min(xs), min(ys), max(xs), max(ys),
                               shape['label'], shape.get('difficult', False))

        writer.save(annotation_path, class_list)

    # ── Create ML ─────────────────────────────────────────────────────────────
    def save_create_ml_format(self, annotation_path, shapes, image_path,
                              image_data, label_hist, line_color, fill_color):
        img = QImage()
        if isinstance(image_data, QImage):
            img = image_data
        elif image_data:
            img.loadFromData(image_data)

        img_size = (img.height(), img.width())
        folder   = os.path.basename(os.path.dirname(image_path))
        filename = os.path.basename(image_path)
        writer   = CreateMLWriter(folder, filename, img_size)
        writer.verified = self.verified

        for shape in shapes:
            pts = shape['points']
            xs  = [p[0] for p in pts]
            ys  = [p[1] for p in pts]
            writer.add_bnd_box(min(xs), min(ys), max(xs), max(ys),
                               shape['label'], shape.get('difficult', False))

        writer.save(annotation_path)

    # ── generic (alias for Pascal VOC) ────────────────────────────────────────
    def save(self, annotation_path, shapes, image_path, image_data,
             line_color, fill_color):
        self.save_pascal_voc_format(annotation_path, shapes, image_path,
                                    image_data, line_color, fill_color)
