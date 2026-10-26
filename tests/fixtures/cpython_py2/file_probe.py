# SPDX-License-Identifier: Apache-2.0
import math
import os
import re


root = "/work/py2/data"
try:
    os.mkdir(root)
except FileExistsError:
    pass
payload = bytes(range(256)) * 12 + b"XOS-PY2"
path = root + "/roundtrip.bin"
with open(path, "wb", buffering=0) as stream:
    assert stream.write(payload) == len(payload)
parts = []
with open(path, "rb", buffering=0) as stream:
    while True:
        part = stream.read(17)
        if not part:
            break
        parts.append(part)
assert b"".join(parts) == payload
assert "roundtrip.bin" in os.listdir(root)
assert os.stat(path).st_size == len(payload)
try:
    open(root + "/missing.bin", "rb")
except FileNotFoundError:
    pass
else:
    raise AssertionError("missing file unexpectedly opened")
assert math.isclose(math.sqrt(144), 12.0)
assert re.fullmatch(r"py[0-9]+", "py2")
print("PY2_FILE_OK", len(payload), len(parts))
