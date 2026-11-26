# SPDX-License-Identifier: Apache-2.0
import argparse
import hashlib
import json
import pathlib
import sys
import tomllib
import xml.etree.ElementTree
import zipfile

archive = "/usr/lib/python314.zip"
assert sys.executable == "/usr/bin/python3"
assert sys.prefix == "/usr"
assert archive in sys.path
assert all(path.startswith(("/usr/", "/tests")) for path in sys.path)
for module in (argparse, hashlib, json, pathlib, tomllib, xml.etree.ElementTree, zipfile):
    assert module.__file__.startswith(archive + "/"), (module.__name__, module.__file__)
print("CPYTHON_XPK_DISK_STDLIB", flush=True)

for fixture in ("startup.py", "py1.py", "a1.py"):
    path = "/tests/" + fixture
    with open(path, "rb") as source:
        code = compile(source.read(), path, "exec")
    exec(code, {"__name__": "__main__", "__file__": path})
