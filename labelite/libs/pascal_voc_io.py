"""Pascal VOC XML format reader / writer."""
import os
import xml.etree.ElementTree as ET
import xml.dom.minidom

from libs.ustr import ustr

XML_EXT  = '.xml'
ENCODE_METHOD = 'utf-8'


class PascalVocReader:
    def __init__(self, file_path):
        self.shapes   = []
        self.verified = False
        self._file_path = file_path
        self._parse()

    def _parse(self):
        tree = ET.parse(self._file_path)
        root = tree.getroot()

        self.verified = root.get('verified', 'no') == 'yes'

        img_size = root.find('size')
        if img_size is not None:
            img_w = int(img_size.findtext('width',  '0'))
            img_h = int(img_size.findtext('height', '0'))
        else:
            img_w = img_h = 0

        for obj in root.findall('object'):
            label     = ustr(obj.findtext('name', ''))
            difficult = int(obj.findtext('difficult', '0')) == 1

            bndbox = obj.find('bndbox')
            if bndbox is None:
                continue
            xmin = float(bndbox.findtext('xmin', '0'))
            ymin = float(bndbox.findtext('ymin', '0'))
            xmax = float(bndbox.findtext('xmax', '0'))
            ymax = float(bndbox.findtext('ymax', '0'))

            points = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
            self.shapes.append((label, points, None, None, difficult))

    def get_shapes(self):
        return self.shapes


class PascalVocWriter:
    def __init__(self, folder_name, file_name, img_size, database_src='Unknown'):
        self.folder_name  = folder_name
        self.file_name    = file_name
        self.img_size     = img_size   # (h, w, channels)
        self.database_src = database_src
        self.box_list     = []
        self.verified     = False

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        bnd_box = {
            'xmin': x_min, 'ymin': y_min,
            'xmax': x_max, 'ymax': y_max,
            'name': name,
            'difficult': difficult,
        }
        self.box_list.append(bnd_box)

    def save(self, target_file):
        root = ET.Element('annotation')
        if self.verified:
            root.set('verified', 'yes')

        ET.SubElement(root, 'folder').text   = self.folder_name
        ET.SubElement(root, 'filename').text = self.file_name
        ET.SubElement(root, 'path').text     = self.file_name

        source = ET.SubElement(root, 'source')
        ET.SubElement(source, 'database').text = self.database_src

        size = ET.SubElement(root, 'size')
        ET.SubElement(size, 'width').text    = str(self.img_size[1] if len(self.img_size) > 1 else 0)
        ET.SubElement(size, 'height').text   = str(self.img_size[0])
        ET.SubElement(size, 'depth').text    = str(self.img_size[2] if len(self.img_size) > 2 else 3)

        ET.SubElement(root, 'segmented').text = '0'

        for box in self.box_list:
            obj = ET.SubElement(root, 'object')
            ET.SubElement(obj, 'name').text      = box['name']
            ET.SubElement(obj, 'pose').text      = 'Unspecified'
            ET.SubElement(obj, 'truncated').text = '0'
            ET.SubElement(obj, 'difficult').text = '1' if box['difficult'] else '0'
            bndbox = ET.SubElement(obj, 'bndbox')
            ET.SubElement(bndbox, 'xmin').text = str(int(box['xmin']))
            ET.SubElement(bndbox, 'ymin').text = str(int(box['ymin']))
            ET.SubElement(bndbox, 'xmax').text = str(int(box['xmax']))
            ET.SubElement(bndbox, 'ymax').text = str(int(box['ymax']))

        raw_str  = ET.tostring(root, encoding=ENCODE_METHOD)
        pretty   = xml.dom.minidom.parseString(raw_str).toprettyxml(indent='  ')
        # Remove the extra XML declaration minidom adds
        lines    = pretty.split('\n')
        pretty   = '\n'.join(lines[1:])   # strip <?xml ...?> line

        with open(target_file, 'w', encoding=ENCODE_METHOD) as f:
            f.write(pretty)
