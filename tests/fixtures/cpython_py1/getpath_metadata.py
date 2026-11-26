# SPDX-License-Identifier: Apache-2.0
import errno
import os
import stat
import sys

assert sys.executable == "/usr/bin/python3"
assert sys.prefix == sys.exec_prefix == "/usr"
assert "/usr/lib/python3.14" in sys.path
assert stat.S_ISREG(os.stat("/usr/bin/python3").st_mode)
assert stat.S_ISDIR(os.stat("/usr/lib/python3.14").st_mode)

for path, expected in (
    ("/work/py1/no-such-file", errno.ENOENT),
    ("/work/py1/main.py/", errno.ENOTDIR),
):
    try:
        os.stat(path)
    except OSError as error:
        assert error.errno == expected, (path, error.errno)
    else:
        raise AssertionError("stat accepted " + path)

print("PY1_GETPATH_METADATA_OK")
