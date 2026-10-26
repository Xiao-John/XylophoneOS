# SPDX-License-Identifier: Apache-2.0
import argparse
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import pathlib
import tomllib
import xml.etree.ElementTree as ElementTree
import zipfile


def check_hash(name, expected):
    actual = getattr(hashlib, name)(b"abc").hexdigest()
    assert actual == expected, (name, actual)


check_hash("md5", "900150983cd24fb0d6963f7d28e17f72")
check_hash("sha1", "a9993e364706816aba3e25717850c26c9cd0d89d")
check_hash("sha256", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
check_hash("sha3_256", "3a985da74fe225b2045c172d6bd390bd855f086e3e9d525b46bfe24511431532")
check_hash("blake2b", "ba80a53f981c4d0d6a2797b69f12f6e94c212f14685ac4b74b12bb6fdbffa2d17d87c5392aab792dc252d5de4533cc9518d38aa8dbf1925ab92386edd4009923")

expected_hmac = "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
assert hmac.new(bytes([0x0b]) * 20, b"Hi There", hashlib.sha256).hexdigest() == expected_hmac

parser = argparse.ArgumentParser()
parser.add_argument("--count", type=int, required=True)
assert parser.parse_args(["--count", "3"]).count == 3


@dataclass(frozen=True)
class Record:
    name: str
    score: int


record = Record("雪", 42)
assert record.name == "雪" and record.score == 42
assert Decimal("1.25") * Decimal("4") == Decimal("5.00")
try:
    import statistics
except OSError as error:
    statistics_status = "blocked_without_system_entropy:" + str(error)
else:
    assert statistics.mean([2, 4, 6]) == 4
    statistics_status = "passed"
config = tomllib.loads('title = "xos"\n[run]\ncount = 3\nenabled = true\n')
assert config["title"] == "xos" and config["run"] == {"count": 3, "enabled": True}
root = ElementTree.fromstring("<root><item value='7'/></root>")
assert root.find("item").attrib["value"] == "7"

directory = pathlib.Path("/work/py3a1/data")
directory.mkdir()
path = directory / "note.txt"
path.write_text("A1 pathlib 雪", encoding="utf-8")
assert path.read_text(encoding="utf-8") == "A1 pathlib 雪"
archive = directory / "stored.zip"
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
    info = zipfile.ZipInfo("note.txt", date_time=(1980, 1, 1, 0, 0, 0))
    bundle.writestr(info, path.read_bytes())
with zipfile.ZipFile(archive) as bundle:
    assert bundle.read("note.txt").decode("utf-8") == "A1 pathlib 雪"

print("PY3_A1_OK hashlib hmac pathlib argparse dataclasses tomllib decimal xml zipfile")
print("PY3_A1_STATISTICS", statistics_status)
