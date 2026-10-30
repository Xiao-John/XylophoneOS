# SPDX-License-Identifier: Apache-2.0
"""Create a deterministic CPython install stage from an accepted build."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TZDATA_WHEEL = ROOT / "src/ports/cpython/upstream/tzdata-2026.5-py2.py3-none-any.whl"
TZDATA_LOCK = ROOT / "src/ports/cpython/tzdata_lock.json"
SKIP_PARTS = {
    "test", "idlelib", "tkinter", "turtledemo", "ensurepip", "lib2to3",
    "__pycache__", "site-packages",
}
SUFFIXES = {".py", ".pyi", ".txt", ".cfg", ".json"}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def accepted_work():
    report_path = ROOT / "build/cpython_py0b_report.json"
    if not report_path.exists():
        raise SystemExit("missing accepted PY0b report")
    report = json.loads(report_path.read_text())
    if report.get("status") != "passed":
        raise SystemExit("PY0b report is not passed")
    fingerprint = report["py0a"]["fingerprint"]
    return ROOT / ".cache/xos_seed/cpython" / fingerprint


def selected_library_files(source):
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.suffix in SUFFIXES:
            yield path, relative


def build_manifest(stage, *, work, build_report, phase):
    files = []
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            files.append({
                "path": "/" + path.relative_to(stage).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            })
    result = {
        "phase": phase,
        "version": build_report["version"],
        "fingerprint": build_report["fingerprint"],
        "sdk_build_id": build_report["sdk_build_id"],
        "source_work": str(work),
        "layout": {
            "interpreter": "/usr/bin/python3",
            "stdlib": "/usr/lib/python3.14",
            "license": "/usr/share/licenses/cpython/LICENSE",
        },
        "files": files,
        "file_count": len(files),
        "status": "staged_not_guest_tested",
    }
    if build_report.get("static_extensions"):
        result["static_extensions"] = build_report["static_extensions"]
    if build_report.get("zlib_prefix"):
        result["dependencies"] = {
            "zlib_version": "1.3.2",
            "zlib_report_sha256": build_report["zlib_report_sha256"],
            "zlib_license": "/usr/share/licenses/zlib/LICENSE",
        }
    if phase == "PY3":
        tzdata = json.loads(TZDATA_LOCK.read_text())
        result["timezone_data"] = {
            "package": "tzdata",
            "version": tzdata["version"],
            "license": tzdata["license"],
            "wheel_sha256": tzdata["wheel_sha256"],
            "license_path": "/usr/share/licenses/tzdata/LICENSE",
        }
    dependencies = result.setdefault("dependencies", {})
    if build_report.get("pillow"):
        pillow = build_report["pillow"]
        dependencies["pillow"] = {"version": pillow["version"],
                                  "archive_sha256": pillow["sha256"],
                                  "builtin_name": pillow["builtin_name"],
                                  "features": pillow["features"],
                                  "license": "/usr/share/licenses/pillow/LICENSE"}
    if build_report.get("sqlite_prefix"):
        receipt = json.loads((Path(build_report["sqlite_prefix"]).parent / "receipt.json").read_text())
        dependencies["sqlite"] = {
            "version": receipt["version"],
            "receipt_sha256": build_report["sqlite_report_sha256"],
            "library_sha256": receipt["library_sha256"],
            "license": "/usr/share/licenses/sqlite/LICENSE",
        }
    if build_report.get("compression_report"):
        report_path = Path(build_report["compression_report"])
        compression = json.loads(report_path.read_text())
        dependencies["compression"] = {
            name: {
                "version": item["version"],
                "library_sha256": item["library_sha256"],
                "license": f"/usr/share/licenses/cpython_{name}/LICENSE",
            }
            for name, item in compression["components"].items()
        }
    if not dependencies:
        result.pop("dependencies", None)
    return result


def install_tzdata(temporary):
    lock = json.loads(TZDATA_LOCK.read_text())
    if TZDATA_WHEEL.name != lock["wheel"] or sha256(TZDATA_WHEEL) != lock["wheel_sha256"]:
        raise ValueError("tzdata wheel checksum does not match the source lock")
    destination = temporary / "usr/lib/python3.14/site-packages"
    destination.mkdir(parents=True, exist_ok=True)
    license_file = None
    with zipfile.ZipFile(TZDATA_WHEEL) as archive:
        for member in archive.infolist():
            path = Path(member.filename)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe path in tzdata wheel: {member.filename}")
            if member.is_dir():
                continue
            output = destination.joinpath(*path.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(archive.read(member))
            if member.filename == lock["license_file_in_wheel"]:
                license_file = output
    if license_file is None:
        raise ValueError("tzdata wheel does not contain its license")
    staged_license = temporary / "usr/share/licenses/tzdata/LICENSE"
    staged_license.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(license_file, staged_license)


def stage_cpython(work, phase="PY1"):
    if phase not in ("PY1", "PY3"):
        raise ValueError("stage phase must be PY1 or PY3")
    work = Path(work).resolve(strict=True)
    build_report = json.loads((work / "py0a_report.json").read_text())
    if build_report.get("status") != "built_not_run":
        raise ValueError("CPython work tree is not a completed static build")
    # PY3B gets an isolated tree so that accepted A-stage manifests remain
    # immutable evidence when new pinned data packages are added.
    stage_name = "stage_py1" if phase == "PY1" else "stage_py3_b"
    output = work / stage_name
    manifest_path = work / f"{stage_name}_manifest.json"
    if output.exists() and manifest_path.exists():
        return output, json.loads(manifest_path.read_text())
    if output.exists() or manifest_path.exists():
        raise ValueError("partial PY1 stage exists; inspect it instead of overwriting")

    with tempfile.TemporaryDirectory(prefix="stage_py1_", dir=work) as folder:
        temporary = Path(folder) / "root"
        binary_dir = temporary / "usr/bin"
        library_dir = temporary / "usr/lib/python3.14"
        license_dir = temporary / "usr/share/licenses/cpython"
        binary_dir.mkdir(parents=True)
        library_dir.mkdir(parents=True)
        license_dir.mkdir(parents=True)
        subprocess.run([
            "x86_64-elf-strip", "-o", str(binary_dir / "python3"),
            str(work / "target_build/python.exe"),
        ], check=True)
        for source, relative in selected_library_files(work / "source/Lib"):
            destination = library_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(
            ROOT / "src/ports/cpython/upstream/LICENSE",
            license_dir / "LICENSE",
        )
        if build_report.get("pillow"):
            pillow = work / "source/Modules/xos_pillow"
            package = library_dir / "site-packages/PIL"
            package.mkdir(parents=True)
            for source_file in sorted((pillow / "src/PIL").rglob("*")):
                if source_file.is_file() and source_file.suffix in {".py", ".pyi"}:
                    target = package / source_file.relative_to(pillow / "src/PIL")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_file, target)
            target = temporary / "usr/share/licenses/pillow/LICENSE"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pillow / "LICENSE", target)
        if phase == "PY3":
            install_tzdata(temporary)
        manifest = build_manifest(temporary, work=work, build_report=build_report, phase=phase)
        if build_report.get("zlib_prefix"):
            license_dir = temporary / "usr/share/licenses/zlib"
            license_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(
                ROOT / "src/ports/cpython/upstream/zlib-LICENSE",
                license_dir / "LICENSE",
            )
            manifest["layout"]["zlib_license"] = "/usr/share/licenses/zlib/LICENSE"
        if build_report.get("sqlite_prefix"):
            receipt = json.loads((Path(build_report["sqlite_prefix"]).parent / "receipt.json").read_text())
            sqlite_lock = json.loads((ROOT / "src/ports/cpython/sqlite/sqlite_lock.json").read_text())
            license_path = ROOT / sqlite_lock["license_file"]
            target = temporary / "usr/share/licenses/sqlite/LICENSE"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(license_path, target)
        if build_report.get("compression_report"):
            compression = json.loads(Path(build_report["compression_report"]).read_text())
            for name, component in compression["components"].items():
                target = temporary / f"usr/share/licenses/cpython_{name}/LICENSE"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(component["license_file"], target)
        manifest["files"] = []
        for path in sorted(temporary.rglob("*")):
            if path.is_file():
                manifest["files"].append({
                    "path": "/" + path.relative_to(temporary).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                })
        manifest["file_count"] = len(manifest["files"])
        os.rename(temporary, output)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return output, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--phase", choices=("PY1", "PY3"), default="PY1")
    args = parser.parse_args()
    stage, manifest = stage_cpython(args.work or accepted_work(), phase=args.phase)
    print(json.dumps({
        "stage": str(stage),
        "manifest": str(stage.parent / f"{stage.name}_manifest.json"),
        "file_count": manifest["file_count"],
        "status": manifest["status"],
    }, indent=2))


if __name__ == "__main__":
    main()
