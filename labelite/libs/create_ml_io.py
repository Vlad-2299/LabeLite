"""Apple Create ML JSON format reader / writer."""
import json
import os

JSON_EXT = '.json'


class CreateMLReader:
    def __init__(self, file_path, image_path):
        self.shapes   = []
        self.verified = False
        self._parse(file_path, image_path)

    def _parse(self, file_path, image_path):
        image_name = os.path.basename(image_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            data = [data]

        for entry in data:
            if entry.get('image') != image_name:
                continue
            for ann in entry.get('annotations', []):
                label = ann.get('label', '')
                coords = ann.get('coordinates', {})
                cx = coords.get('x', 0)
                cy = coords.get('y', 0)
                w  = coords.get('width',  0)
                h  = coords.get('height', 0)
                x1, y1 = cx - w / 2, cy - h / 2
                x2, y2 = cx + w / 2, cy + h / 2
                points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
                self.shapes.append((label, points, None, None, False))

    def get_shapes(self):
        return self.shapes


class CreateMLWriter:
    def __init__(self, folder_name, file_name, img_size):
        self.folder_name = folder_name
        self.file_name   = file_name
        self.img_size    = img_size
        self.box_list    = []
        self.verified    = False

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        self.box_list.append({
            'xmin': x_min, 'ymin': y_min,
            'xmax': x_max, 'ymax': y_max,
            'name': name,
        })

    def save(self, target_file):
        annotations = []
        for box in self.box_list:
            cx = (box['xmin'] + box['xmax']) / 2.0
            cy = (box['ymin'] + box['ymax']) / 2.0
            bw = box['xmax'] - box['xmin']
            bh = box['ymax'] - box['ymin']
            annotations.append({
                'label': box['name'],
                'coordinates': {
                    'x': cx, 'y': cy,
                    'width': bw, 'height': bh,
                },
            })

        out = [{
            'image':       self.file_name,
            'annotations': annotations,
        }]

        # If file exists, merge with existing entries
        if os.path.exists(target_file):
            with open(target_file, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, list):
                existing = [e for e in existing if e.get('image') != self.file_name]
                out = existing + out

        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(out, f, indent=2)
