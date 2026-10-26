# SPDX-License-Identifier: Apache-2.0
"""Build a pinned static zlib for the CPython XOS cross build."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/cpython"
DEFAULT_ARCHIVE = ROOT / ".cache/xos_seed/cpython/sources/zlib-1.3.2.tar.xz"
DEFAULT_SDK = ROOT / "build/threading_sdk"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def executable(name):
    value = shutil.which(name)
    if value is None:
        raise FileNotFoundError(f"required cross tool not found: {name}")
    return value


def run(command, *, cwd, env, log):
    with Path(log).open("w") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)


def extract_source(archive, destination, expected_root):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        roots = {Path(member.name).parts[0] for member in bundle.getmembers() if member.name}
        if roots != {expected_root}:
            raise ValueError(f"unexpected zlib archive roots: {sorted(roots)}")
        for member in bundle.getmembers():
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    lock = json.loads((PORT / "zlib_lock.json").read_text())
    archive_hash = sha256(archive)
    license_hash = sha256(PORT / "upstream/zlib-LICENSE")
    if archive_hash != lock["sha256"]:
        parser.error("zlib archive SHA-256 does not match zlib_lock.json")
    if license_hash != lock["license_sha256"]:
        parser.error("zlib license hash does not match zlib_lock.json")

    cc = os.environ.get("XOS_CC") or executable("x86_64-elf-gcc")
    ar = os.environ.get("XOS_AR") or executable("x86_64-elf-ar")
    ranlib = os.environ.get("XOS_RANLIB") or executable("x86_64-elf-ranlib")
    sdk_manifest = sdk / "manifest.json"
    sdk_hash = sha256(sdk_manifest)
    fingerprint_inputs = {
        "archive_sha256": archive_hash,
        "build_script_sha256": sha256(__file__),
        "cc": cc,
        "ar": ar,
        "ranlib": ranlib,
        "sdk_manifest_sha256": sdk_hash,
        "zlib_lock_sha256": sha256(PORT / "zlib_lock.json"),
        "xos_patch_sha256": sha256(PORT / "zlib_patches/0001_xos_errno_header.patch"),
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_inputs, sort_keys=True).encode()
    ).hexdigest()[:20]
    work = ROOT / ".cache/xos_seed/cpython/zlib" / fingerprint
    if work.exists():
        report_path = work / "report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            if report.get("status") == "built" and report.get("fingerprint") == fingerprint:
                print(json.dumps(report, indent=2, sort_keys=True))
                return
        raise FileExistsError(f"partial zlib work directory exists; inspect it: {work}")

    work.mkdir(parents=True)
    source = work / "source"
    build = work / "target_build"
    prefix = work / "prefix"
    build.mkdir()
    extract_source(archive, source, f"zlib-{lock['version']}")

    env = dict(os.environ)
    env.update(
        CC=cc,
        AR=ar,
        RANLIB=ranlib,
        CFLAGS=" ".join([
            "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic",
            "-fno-stack-protector", "-ffunction-sections", "-fdata-sections",
            "-D__xos__=1", "-isystem", str(sdk / "include"),
        ]),
    )
    run(
        [
            "patch", "-p1", "--forward", "-i",
            str(PORT / "zlib_patches/0001_xos_errno_header.patch"),
        ],
        cwd=source,
        env=env,
        log=work / "patch.log",
    )
    report = {
        "phase": "PY3-A2-zlib",
        "status": "build_started",
        "version": lock["version"],
        "fingerprint": fingerprint,
        "inputs": fingerprint_inputs,
        "source_archive_sha256": archive_hash,
        "license_sha256": license_hash,
        "sdk_path": str(sdk),
        "sdk_manifest_sha256": sdk_hash,
        "prefix": str(prefix),
    }
    try:
        run(
            ["/bin/sh", str(source / "configure"), "--static", f"--prefix={prefix}"],
            cwd=build,
            env=env,
            log=work / "configure.log",
        )
        run(
            ["make", "-j2", f"AR={ar}", "ARFLAGS=rc", "libz.a"],
            cwd=build,
            env=env,
            log=work / "make.log",
        )
        include = prefix / "include"
        library = prefix / "lib"
        include.mkdir(parents=True)
        library.mkdir(parents=True)
        shutil.copyfile(source / "zlib.h", include / "zlib.h")
        shutil.copyfile(build / "zconf.h", include / "zconf.h")
        shutil.copyfile(build / "libz.a", library / "libz.a")
        archive_members = subprocess.check_output(
            [ar, "t", str(library / "libz.a")], text=True
        ).splitlines()
        if len(archive_members) < 10 or (library / "libz.a").stat().st_size < 1000:
            raise ValueError("libz.a does not contain the expected object members")
        report.update({
            "status": "built",
            "header_sha256": {
                "zlib.h": sha256(include / "zlib.h"),
                "zconf.h": sha256(include / "zconf.h"),
            },
            "libz_sha256": sha256(library / "libz.a"),
            "libz_bytes": (library / "libz.a").stat().st_size,
            "libz_members": archive_members,
        })
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise
    (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
