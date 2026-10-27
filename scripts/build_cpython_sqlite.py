# SPDX-License-Identifier: Apache-2.0
"""Build the isolated, static SQLite dependency profile used by XOS CPython."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/cpython/sqlite"
DEFAULT_ARCHIVE = ROOT / ".cache/xos_seed/cpython/sqlite/sqlite-autoconf-3540100.tar.gz"
DEFAULT_SDK = ROOT / "build/threading_sdk"
OUTPUT_ROOT = ROOT / ".cache/xos_seed/cpython/sqlite/builds"
FLAGS = [
    "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
    "-ffunction-sections", "-fdata-sections", "-D__xos__=1",
    "-DSQLITE_OS_OTHER=1", "-DSQLITE_THREADSAFE=0",
    "-DSQLITE_OMIT_LOAD_EXTENSION=1", "-DSQLITE_OMIT_WAL=1",
    "-DSQLITE_TEMP_STORE=3", "-DSQLITE_DQS=0",
]


def digest(path, algorithm="sha256"):
    hasher = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def executable(name):
    value = shutil.which(name)
    if value is None:
        raise FileNotFoundError(f"required cross tool not found: {name}")
    return value


def safe_extract(archive, destination, expected_root):
    destination.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        roots = {Path(member.name).parts[0] for member in members if member.name}
        if roots != {expected_root}:
            raise ValueError(f"unexpected SQLite archive roots: {sorted(roots)}")
        for member in members:
            parts = Path(member.name).parts
            if not parts or Path(member.name).is_absolute() or ".." in parts:
                raise ValueError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"archive link not admitted: {member.name}")
            relative = parts[1:]
            if not relative:
                continue
            target = destination.joinpath(*relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"archive member has no data: {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
            else:
                raise ValueError(f"unsupported archive member: {member.name}")


def run(command, cwd, env, log):
    with Path(log).open("w") as output:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=output,
                                 stderr=subprocess.STDOUT)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    lock_path = PORT / "sqlite_lock.json"
    lock = json.loads(lock_path.read_text())
    sha256 = digest(archive)
    sha3 = digest(archive, "sha3_256")
    license_path = ROOT / lock["license_file"]
    license_sha256 = digest(license_path)
    if archive.stat().st_size != lock["archive_bytes"]:
        parser.error("SQLite archive size does not match sqlite_lock.json")
    if sha256 != lock["sha256"] or sha3 != lock["sha3_256"]:
        parser.error("SQLite archive hashes do not match sqlite_lock.json")
    if license_sha256 != lock["license_sha256"]:
        parser.error("SQLite license hash does not match sqlite_lock.json")
    sdk_manifest = sdk / "manifest.json"
    sdk_hash = digest(sdk_manifest)
    cc = os.environ.get("XOS_CC") or executable("x86_64-elf-gcc")
    ar = os.environ.get("XOS_AR") or executable("x86_64-elf-ar")
    ranlib = os.environ.get("XOS_RANLIB") or executable("x86_64-elf-ranlib")
    inputs = {
        "archive_sha256": sha256,
        "archive_sha3_256": sha3,
        "builder_sha256": digest(__file__),
        "lock_sha256": digest(lock_path),
        "license_sha256": license_sha256,
        "vfs_sha256": digest(PORT / "xos_vfs.c"),
        "cc": cc,
        "ar": ar,
        "ranlib": ranlib,
        "sdk_manifest_sha256": sdk_hash,
        "compile_flags": FLAGS,
    }
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    if OUTPUT_ROOT.resolve() != (ROOT / ".cache/xos_seed/cpython/sqlite/builds").resolve():
        raise RuntimeError("unsafe SQLite output root")
    work = OUTPUT_ROOT / fingerprint
    if work.exists():
        receipt = work / "receipt.json"
        if receipt.is_file():
            prior = json.loads(receipt.read_text())
            if prior.get("status") == "built" and prior.get("fingerprint") == fingerprint:
                print(json.dumps(prior, indent=2, sort_keys=True))
                return
        raise FileExistsError(f"incomplete SQLite build directory exists; inspect it: {work}")
    work.mkdir(parents=True)
    source = work / "source"
    objects = work / "objects"
    prefix = work / "prefix"
    objects.mkdir()
    major, minor, patch = (int(part) for part in lock["version"].split("."))
    archive_root = f"sqlite-autoconf-{major}{minor:02d}{patch:02d}00"
    safe_extract(archive, source, archive_root)
    upstream = source / "sqlite3.c"
    if not upstream.is_file():
        raise FileNotFoundError(upstream)
    include_flags = [f"-isystem{sdk / 'include'}", f"-I{source}", f"-I{PORT}"]
    common = [cc, *FLAGS, *include_flags, "-std=c99", "-Wall", "-Wextra"]
    env = dict(os.environ)
    report = {
        "phase": "PY3-B3-sqlite-static-preparation",
        "status": "build_started",
        "version": lock["version"],
        "fingerprint": fingerprint,
        "inputs": inputs,
        "source": lock["source"],
        "source_archive_sha256": sha256,
        "source_archive_sha3_256": sha3,
        "sdk_path": str(sdk),
        "prefix": str(prefix),
        "profile": "single_process_exclusive_lock_rollback_journal_no_wal",
        "integration_hooks": ["libc fsync(fd)", "libc ftruncate(fd, size)"],
        "acceptance": "static preparation only; guest persistence requires the integration hooks",
    }
    try:
        sqlite_obj = objects / "sqlite3.o"
        vfs_obj = objects / "xos_vfs.o"
        run([*common, "-c", str(upstream), "-o", str(sqlite_obj)], work, env, work / "sqlite_compile.log")
        run([*common, "-c", str(PORT / "xos_vfs.c"), "-o", str(vfs_obj)], work, env, work / "vfs_compile.log")
        prefix_include = prefix / "include"
        prefix_lib = prefix / "lib"
        prefix_include.mkdir(parents=True)
        prefix_lib.mkdir(parents=True)
        shutil.copyfile(source / "sqlite3.h", prefix_include / "sqlite3.h")
        shutil.copyfile(source / "sqlite3ext.h", prefix_include / "sqlite3ext.h")
        shutil.copyfile(PORT / "UPSTREAM_LICENSE.md", prefix_include / "SQLITE_LICENSE.md")
        shutil.copyfile(PORT / "README.md", prefix_include / "XOS_SQLITE_PROFILE.md")
        library = prefix_lib / "libsqlite3.a"
        run([ar, "rc", str(library), str(sqlite_obj), str(vfs_obj)], work, env, work / "archive.log")
        run([ranlib, str(library)], work, env, work / "ranlib.log")
        members = subprocess.check_output([ar, "t", str(library)], text=True).splitlines()
        nm = os.environ.get("XOS_NM") or executable("x86_64-elf-nm")
        undefined = subprocess.check_output([nm, "-u", str(sqlite_obj), str(vfs_obj)], text=True, stderr=subprocess.STDOUT)
        report.update({
            "status": "built",
            "library": str(library),
            "library_sha256": digest(library),
            "library_bytes": library.stat().st_size,
            "archive_members": members,
            "header_sha256": {
                "sqlite3.h": digest(prefix_include / "sqlite3.h"),
                "sqlite3ext.h": digest(prefix_include / "sqlite3ext.h"),
            },
            "expected_unresolved_runtime_symbols": ["fsync", "ftruncate"],
            "object_undefined_summary": undefined[-3000:],
        })
    except Exception as error:
        report.update(status="failed", error=str(error))
        (work / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise
    (work / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
