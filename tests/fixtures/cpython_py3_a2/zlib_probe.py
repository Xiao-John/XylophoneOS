# SPDX-License-Identifier: Apache-2.0
import gzip
import io
import pathlib
import sys
import zipfile
import zlib


payload = (b"XOS zlib static profile / deflate / CRC / " + bytes(range(64))) * 300
packed = zlib.compress(payload, level=6)
assert zlib.decompress(packed) == payload

compressor = zlib.compressobj(level=6, wbits=zlib.MAX_WBITS)
streamed = b"".join(compressor.compress(payload[index:index + 37])
                    for index in range(0, len(payload), 37))
streamed += compressor.flush()
decompressor = zlib.decompressobj()
restored = b"".join(decompressor.decompress(streamed[index:index + 19])
                    for index in range(0, len(streamed), 19))
restored += decompressor.flush()
assert restored == payload and decompressor.eof

gzip_path = pathlib.Path("/work/py3a2/payload.gz")
gzip_path.write_bytes(gzip.compress(payload, mtime=0))
assert gzip.decompress(gzip_path.read_bytes()) == payload

zip_path = pathlib.Path("/work/py3a2/payload.zip")
info = zipfile.ZipInfo("payload.bin", date_time=(1980, 1, 1, 0, 0, 0))
info.compress_type = zipfile.ZIP_DEFLATED
module_info = zipfile.ZipInfo("py3a2_zipmod.py", date_time=(1980, 1, 1, 0, 0, 0))
module_info.compress_type = zipfile.ZIP_DEFLATED
with zipfile.ZipFile(zip_path, "w") as bundle:
    bundle.writestr(info, payload)
    bundle.writestr(module_info, "VALUE = 'zipimport works'\n")
with zipfile.ZipFile(zip_path) as bundle:
    assert bundle.read("payload.bin") == payload

sys.path.insert(0, str(zip_path))
import py3a2_zipmod
assert py3a2_zipmod.VALUE == "zipimport works"

try:
    zlib.decompress(packed[:-1])
except zlib.error:
    pass
else:
    raise AssertionError("truncated zlib stream was accepted")

corrupt = packed[:-4] + b"\x00\x00\x00\x00"
try:
    zlib.decompress(corrupt)
except zlib.error:
    pass
else:
    raise AssertionError("bad Adler checksum was accepted")

bad_gzip = gzip_path.read_bytes()[:-8]
try:
    gzip.decompress(bad_gzip)
except (OSError, EOFError):
    pass
else:
    raise AssertionError("truncated gzip stream was accepted")

zip_bytes = bytearray(zip_path.read_bytes())
central = zip_bytes.find(b"PK\x01\x02")
assert central >= 0
zip_bytes[central + 16] ^= 1
try:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as bundle:
        bundle.read("payload.bin")
except zipfile.BadZipFile:
    pass
else:
    raise AssertionError("bad ZIP CRC was accepted")

print("PY3_A2_OK zlib streaming gzip deflate_zip zipimport truncated corrupted crc")
