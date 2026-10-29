# SPDX-License-Identifier: Apache-2.0
"""Exercise unmodified Pillow against its real statically linked C core."""
import io
import hashlib
import json
import sys
import threading
import struct
import zlib
from PIL import Image, PngImagePlugin, BmpImagePlugin, ImageChops, features

assert 'PIL._imaging' in sys.builtin_module_names
assert Image.core.PILLOW_VERSION == '11.3.0'
assert features.check_codec('zlib') and not features.check_codec('jpg')
raw = bytes(v for y in range(16) for x in range(16)
            for v in ((x * 17) % 256, (y * 17) % 256, ((x + y) * 11) % 256))
image = Image.frombytes('RGB', (16, 16), raw)
assert image.tobytes() == raw
flip = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
expected = b''.join(raw[(y * 16 + x) * 3:(y * 16 + x + 1) * 3]
                    for y in range(16) for x in reversed(range(16)))
assert flip.tobytes() == expected
assert image.crop((2, 3, 9, 11)).size == (7, 8)
assert image.resize((32, 32), Image.Resampling.NEAREST).getpixel((30, 30)) == image.getpixel((15, 15))
assert ImageChops.difference(image, image).getbbox() is None
for format in ('PNG', 'BMP'):
    destination = '/work/pillow-' + format.lower() + '.bin'
    image.save(destination, format=format)
    with Image.open(destination) as decoded:
        decoded.load()
        assert decoded.format == format and decoded.size == (16, 16)
        assert decoded.convert('RGB').tobytes() == raw
    print('IMAGING_FILE:' + json.dumps({'format': format, 'path': destination,
          'sha256': hashlib.sha256(open(destination, 'rb').read()).hexdigest(),
          'raw_sha256': hashlib.sha256(raw).hexdigest()}), flush=True)
try:
    Image.open(io.BytesIO(b'\x89PNG\r\n\x1a\n'))
except (OSError, ValueError):
    pass
else:
    raise AssertionError('truncated PNG accepted')
try:
    Image.new('RGB', (-1, 3))
except ValueError:
    pass
else:
    raise AssertionError('negative width accepted')
header = struct.pack('>IIBBBBB', 50000, 50000, 8, 2, 0, 0, 0)
chunk = b'IHDR' + header
bomb = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', len(header)) + chunk + struct.pack('>I', zlib.crc32(chunk))
bomb += struct.pack('>I', 0) + b'IDAT' + struct.pack('>I', zlib.crc32(b'IDAT'))
bomb += struct.pack('>I', 0) + b'IEND' + struct.pack('>I', zlib.crc32(b'IEND'))
try:
    Image.open(io.BytesIO(bomb))
except Image.DecompressionBombError:
    pass
else:
    raise AssertionError('default decompression bomb guard did not reject dimensions')
failures = []
def worker():
    try:
        for _ in range(20):
            local = Image.frombytes('RGB', (16, 16), raw)
            encoded = io.BytesIO(); local.save(encoded, format='PNG')
            with Image.open(io.BytesIO(encoded.getvalue())) as decoded:
                assert decoded.tobytes() == raw
    except BaseException as error:
        failures.append(repr(error))
threads = [] if sys.argv[1:] == ['single'] else [threading.Thread(target=worker) for _ in range(2)]
for thread in threads: thread.start()
for thread in threads: thread.join()
assert not failures, failures
print('IMAGING_OK:' + json.dumps({'version': Image.core.PILLOW_VERSION,
      'builtin': 'PIL._imaging', 'thread_roundtrips': len(threads) * 20,
      'raw_sha256': hashlib.sha256(raw).hexdigest()}), flush=True)
