"""YOLO TXT format reader / writer."""
import os
from libs.ustr import ustr

TXT_EXT = '.txt'


def _find_class_names(label_dir, label_hist):
    """Return class names: classes.txt in the annotation folder, else label_hist."""
    classes_path = os.path.join(label_dir, 'classes.txt')
    if os.path.exists(classes_path):
        with open(classes_path, 'r', encoding='utf-8') as f:
            names = [l.strip() for l in f if l.strip()]
        if names:
            return names
    return list(label_hist) if label_hist else []


class YoloReader:
    def __init__(self, file_path, image, label_hist=None):
        self.shapes    = []
        self.verified  = False
        self._parse(file_path, image, label_hist or [])

    def _parse(self, file_path, image, label_hist):
        img_w = image.width()
        img_h = image.height()
        if img_w == 0 or img_h == 0:
            return

        label_dir    = os.path.dirname(file_path)
        class_names  = _find_class_names(label_dir, label_hist)

        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 5:
                    continue
                try:
                    cls_id = int(parts[0])
                    cx, cy, w, h = map(float, parts[1:5])
                except ValueError:
                    continue

                x1 = (cx - w / 2) * img_w
                y1 = (cy - h / 2) * img_h
                x2 = (cx + w / 2) * img_w
                y2 = (cy + h / 2) * img_h

                label = (class_names[cls_id]
                         if 0 <= cls_id < len(class_names)
                         else str(cls_id))

                points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                self.shapes.append((label, points, None, None, False))

    def get_shapes(self):
        return self.shapes


class YoloWriter:
    def __init__(self, folder_name, file_name, img_size):
        self.folder_name = folder_name
        self.file_name   = file_name
        self.img_size    = img_size   # (h, w)
        self.verified    = False
        self.box_list    = []

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        self.box_list.append({
            'xmin': x_min, 'ymin': y_min,
            'xmax': x_max, 'ymax': y_max,
            'name': name,
            'difficult': difficult,
        })

    def save(self, target_file, class_list):
        img_h, img_w = float(self.img_size[0]), float(self.img_size[1])
        lines = []
        for box in self.box_list:
            name = box['name']
            if name in class_list:
                cls_id = class_list.index(name)
            else:
                # Append unknown class at end
                class_list.append(name)
                cls_id = len(class_list) - 1

            cx = ((box['xmin'] + box['xmax']) / 2.0) / img_w
            cy = ((box['ymin'] + box['ymax']) / 2.0) / img_h
            bw = (box['xmax'] - box['xmin']) / img_w
            bh = (box['ymax'] - box['ymin']) / img_h
            lines.append(f'{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}')

        with open(target_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
            if lines:
                f.write('\n')

        # Also write / update classes.txt next to the annotation file
        classes_path = os.path.join(os.path.dirname(target_file), 'classes.txt')
        with open(classes_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(class_list) + '\n')
