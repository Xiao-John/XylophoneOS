# SPDX-License-Identifier: Apache-2.0
"""Convert one locked pure-Python wheel into a bounded XPK package."""

import argparse
import base64
import csv
import hashlib
import io
import json
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from xypm_format import DEFAULT_PROFILE, PackageError, load_json, pack_package, sha_file

MAX_WHEEL = 16 << 20
MAX_MEMBERS = 512
MAX_MEMBER = 4 << 20
SITE = "usr/lib/python3.14/site-packages"
DEFAULT_PROFILE = ROOT / "config/package/xos_x86_64_static_single_b2_v1.json"


def require(condition, message):
    if not condition:
        raise PackageError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_member(name):
    require("\\" not in name and not name.startswith("/"), "unsafe wheel member path")
    path = PurePosixPath(name)
    require(path.parts and all(part not in ("", ".", "..") for part in path.parts), "unsafe wheel member path")
    require(all(re.fullmatch(r"[A-Za-z0-9_.+-]+", part) for part in path.parts), "unsupported wheel member name")
    require(not name.endswith("/"), "directory members are not accepted")
    require(not name.lower().endswith((".so", ".pyd", ".dll", ".dylib", ".exe", ".pth")),
            "native modules, executables and .pth files are rejected")
    return path


def read_wheel(wheel, lock):
    wheel = Path(wheel).resolve(strict=True)
    require(wheel.stat().st_size <= MAX_WHEEL, "wheel exceeds 16 MiB")
    require(wheel.name == lock["filename"], "wheel filename does not match lock")
    actual_hash = sha_file(wheel)
    require(actual_hash == lock["wheel_sha256"], "wheel SHA256 does not match lock")
    with zipfile.ZipFile(wheel) as archive:
        infos = archive.infolist()
        require(0 < len(infos) <= MAX_MEMBERS, "invalid wheel member count")
        members = {}
        total = 0
        for info in infos:
            path = safe_member(info.filename)
            mode = info.external_attr >> 16
            require(not stat.S_ISLNK(mode), "wheel symlinks are rejected")
            require(info.file_size <= MAX_MEMBER, "wheel member exceeds 4 MiB")
            total += info.file_size
            require(total <= MAX_WHEEL, "expanded wheel exceeds 16 MiB")
            require(info.filename not in members, "duplicate wheel member")
            members[info.filename] = archive.read(info)

    dist_info = f'{lock["name"]}-{lock["version"]}.dist-info'
    wheel_meta_path = f"{dist_info}/WHEEL"
    record_path = f"{dist_info}/RECORD"
    license_path = f"{dist_info}/licenses/LICENSE.md"
    require(wheel_meta_path in members and record_path in members and license_path in members,
            "wheel lacks required WHEEL, RECORD, or license metadata")
    metadata = members[wheel_meta_path].decode("utf-8", "strict")
    require("Root-Is-Purelib: true" in metadata.splitlines(), "wheel is not marked pure Python")
    require(f'Tag: py3-none-any' in metadata.splitlines(), "wheel is not tagged py3-none-any")
    rows = list(csv.reader(io.StringIO(members[record_path].decode("utf-8", "strict"))))
    require(all(len(row) == 3 for row in rows), "invalid wheel RECORD row")
    recorded = {}
    for name, encoded_hash, encoded_size in rows:
        safe_member(name)
        require(name not in recorded, "duplicate RECORD entry")
        recorded[name] = (encoded_hash, encoded_size)
    require(set(recorded) == set(members), "RECORD membership differs from wheel archive")
    for name, data in members.items():
        encoded_hash, encoded_size = recorded[name]
        if name == record_path:
            require(not encoded_hash and not encoded_size, "RECORD must not hash itself")
            continue
        expected = "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        require(encoded_hash == expected and encoded_size == str(len(data)), "wheel RECORD hash/size mismatch")
    license_bytes = members[license_path]
    preserved_license = ROOT / "src/ports/cpython/upstream/idna-LICENSE.md"
    require(sha_file(preserved_license) == lock["license_sha256"] and
            hashlib.sha256(license_bytes).hexdigest() == lock["license_sha256"],
            "wheel and preserved license do not match lock")
    return wheel, members, dist_info, license_path, actual_hash


def convert(wheel, lock_path, output, profile_path=DEFAULT_PROFILE):
    lock = load_json(lock_path)
    require(set(lock) == {"name", "version", "filename", "source", "wheel_url", "wheel_sha256", "license_sha256"},
            "unexpected lock fields")
    wheel, members, dist_info, license_path, wheel_hash = read_wheel(wheel, lock)
    profile = load_json(profile_path)
    package_id = "python_" + lock["name"].replace("-", "_")
    with tempfile.TemporaryDirectory(prefix="xypm_python_wheel_") as directory:
        package_root = Path(directory)
        files = []

        def add(path, data, role="data"):
            destination = package_root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            files.append({"path": path, "type": "file", "size": len(data), "sha256": digest(data), "role": role})

        for name, data in sorted(members.items()):
            if name == f"{dist_info}/RECORD" or name.startswith(dist_info + "/licenses/"):
                continue
            add(f"{SITE}/{name}", data)
        license_data = members[license_path]
        license_dest = f"usr/share/licenses/{package_id}/LICENSE.md"
        add(license_dest, license_data)
        receipt_path = f"usr/share/{package_id}/build_receipt.json"
        receipt = {
            "format": 1,
            "package": package_id,
            "version": lock["version"],
            "wheel_filename": wheel.name,
            "wheel_sha256": wheel_hash,
            "source": lock["source"],
            "license_sha256": digest(license_data),
            "destination": "/usr/lib/python3.14/site-packages",
        }
        receipt_data = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
        add(receipt_path, receipt_data)
        manifest = {
            "format_version": 1,
            "id": package_id,
            "upstream_version": lock["version"],
            "revision": 0,
            "target_profile": profile["id"],
            "required_features": [],
            "runtime_dependencies": [],
            "files": files,
            "licenses": [license_dest],
            "build_receipt": {"path": receipt_path, "sha256": digest(receipt_data)},
            "source": lock["source"] + " wheel_sha256=" + wheel_hash,
        }
        manifest_path = package_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        pack_package(package_root, manifest, output)
    return {"status": "packed", "id": package_id, "version": lock["version"],
            "wheel_sha256": wheel_hash, "package_sha256": sha_file(output),
            "payload_files": len(files), "output": str(Path(output).resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--lock", type=Path, default=ROOT / "src/ports/cpython/idna_lock.json")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(convert(args.wheel, args.lock, args.output, args.profile), indent=2))
        return 0
    except (PackageError, OSError, UnicodeError, zipfile.BadZipFile, csv.Error, KeyError) as error:
        print("xypm-python-wheel: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
