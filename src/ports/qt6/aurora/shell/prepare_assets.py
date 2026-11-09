"""Compile the preserved GUI-Desktop artwork (host dependency: PySide6)."""
from pathlib import Path
import hashlib
import json
from xml.etree.ElementTree import Element, SubElement, ElementTree
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QRectF

root = Path(__file__).resolve().parent
out = root / 'generated'
out.mkdir(exist_ok=True)
rcc = Element('RCC')
resource = SubElement(rcc, 'qresource', prefix='/aurora')
bindings = {}
for source in sorted((root / 'artwork/icon').rglob('*.svg')):
    relative = source.relative_to(root / 'artwork').as_posix()
    destination = out / (source.stem + '.argb')
    image = QImage(192, 192, QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise RuntimeError(f'Invalid SVG: {source}')
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 192, 192))
    painter.end()
    destination.write_bytes(bytes(image.constBits()))
    SubElement(resource, 'file', alias=relative).text = destination.relative_to(root).as_posix()
    bindings[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
# Preserve every part of the image. Downsample only; the widget stretches it to
# the negotiated display rectangle exactly as the original Background does.
image = QImage(str(root / 'artwork/Curvive.png'))
if image.isNull():
    raise RuntimeError('Wallpaper missing')
from PySide6.QtCore import Qt
image = image.scaledToWidth(1024, Qt.SmoothTransformation)
if not image.save(str(out / 'wallpaper.bmp'), 'BMP'):
    raise RuntimeError('Wallpaper conversion failed')
SubElement(resource, 'file', alias='wallpaper.bmp').text = 'generated/wallpaper.bmp'
ElementTree(rcc).write(root / 'shell.qrc', encoding='utf-8')
bindings['Curvive.png'] = hashlib.sha256((root / 'artwork/Curvive.png').read_bytes()).hexdigest()
(out / 'artwork.json').write_text(json.dumps(bindings, indent=2) + '\n')
