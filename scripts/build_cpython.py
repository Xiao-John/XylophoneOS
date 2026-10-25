# SPDX-License-Identifier: Apache-2.0
"""Run the isolated CPython PY0a cross-configuration probe."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/cpython"
DEFAULT_ARCHIVE = ROOT / ".cache/xos_seed/cpython/sources/Python-3.14.9.tar.xz"
DEFAULT_SDK = ROOT / "build/releases/0.0.1-1024/sdk"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_tree(root):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[str(path.relative_to(root))] = sha256(path)
    return result


def run(command, *, cwd, env=None, log=None):
    if log is None:
        subprocess.run(command, cwd=cwd, env=env, check=True)
        return
    with log.open("w") as stream:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)


def extract_source(archive, destination):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        roots = {Path(member.name).parts[0] for member in members if member.name}
        if len(roots) != 1:
            raise ValueError("CPython archive must contain one top-level directory")
        for member in members:
            parts = Path(member.name).parts
            if not parts or Path(member.name).is_absolute() or ".." in parts:
                raise ValueError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"archive link not admitted: {member.name}")
            member.name = str(Path(*parts[1:]))
            if member.name != ".":
                # Python 3.9 lacks tarfile's filter= API. The checks above
                # admit only regular directories/files below destination.
                bundle.extract(member, destination)


def apply_patches(source):
    series = (PORT / "patches/series").read_text().splitlines()
    for name in (line.strip() for line in series):
        if not name or name.startswith("#"):
            continue
        run(
            ["patch", "-p1", "--forward", "-i", str(PORT / "patches" / name)],
            cwd=source,
        )


def python_version(executable):
    script = "import json,sys;print(json.dumps(list(sys.version_info[:3])))"
    output = subprocess.check_output([str(executable), "-S", "-c", script], text=True)
    return tuple(json.loads(output))


def ensure_build_python(source, work, expected, supplied):
    if supplied is not None:
        executable = supplied.resolve(strict=True)
    else:
        build = work / "host_build"
        build.mkdir(exist_ok=True)
        candidates = (build / "python.exe", build / "python")
        executable = next((path for path in candidates if path.exists()), None)
        if executable is None:
            run(
                [
                    str(source / "configure"),
                    f"--prefix={build / 'install'}",
                    "--without-ensurepip",
                    "--disable-test-modules",
                    "--without-mimalloc",
                ],
                cwd=build,
                log=work / "host_configure.log",
            )
            target = "python.exe" if sys.platform == "darwin" else "python"
            run(
                ["make", "-j2", target],
                cwd=build,
                log=work / "host_make.log",
            )
            executable = build / target
    actual = python_version(executable)
    if actual != expected:
        raise ValueError(f"build Python {actual} does not match target {expected}")
    return executable


def tool(name):
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"required cross tool not found: {name}")
    return executable


def build_xos_bridge(work, sdk):
    output = work / "xos_time.o"
    if output.exists():
        return output
    cxx = os.environ.get("XOS_CXX") or tool("x86_64-elf-g++")
    run(
        [
            cxx,
            "-O2",
            "-mno-red-zone",
            "-fno-pie",
            "-fno-pic",
            "-fno-stack-protector",
            "-fno-exceptions",
            "-fno-rtti",
            "-isystem",
            str(sdk / "include"),
            "-c",
            str(PORT / "xos_time.cpp"),
            "-o",
            str(output),
        ],
        cwd=work,
    )
    return output


def target_environment(sdk, build_python, bridge):
    cc = os.environ.get("XOS_CC") or tool("x86_64-elf-gcc")
    cxx = os.environ.get("XOS_CXX") or tool("x86_64-elf-g++")
    ar = os.environ.get("XOS_AR") or tool("x86_64-elf-ar")
    ranlib = os.environ.get("XOS_RANLIB") or tool("x86_64-elf-ranlib")
    readelf = os.environ.get("XOS_READELF") or tool("x86_64-elf-readelf")
    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()
    cflags = [
        "-O2",
        "-mno-red-zone",
        "-fno-pie",
        "-fno-pic",
        "-fno-stack-protector",
        "-ffunction-sections",
        "-fdata-sections",
    ]
    # LDFLAGS is duplicated into PY_LDFLAGS by CPython's Makefile, and GNU ld
    # rejects the same linker script twice. Keep -L/-T/crt0 in LIBS instead,
    # where they appear exactly once.
    ldflags = [
        "-nostdlib",
        "-static",
        "-no-pie",
        "-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
    ]
    libraries = [
        "-L",
        str(sdk / "lib"),
        "-T",
        str(sdk / "user.ld"),
        str(sdk / "crt0_posix.o"),
        str(bridge),
        "-Wl,--start-group",
        str(sdk / "lib/libxos.a"),
        str(sdk / "lib/libxos_loader.a"),
        str(sdk / "lib/libc.a"),
        str(sdk / "lib/libm.a"),
        libgcc,
        "-Wl,--end-group",
    ]
    env = dict(os.environ)
    env.update(
        CC=cc,
        CXX=cxx,
        AR=ar,
        RANLIB=ranlib,
        READELF=readelf,
        CFLAGS=shlex.join(cflags),
        CPPFLAGS=shlex.join(
            ["-D__xos__=1", "-isystem", str(sdk / "include")]
        ),
        LDFLAGS=shlex.join(ldflags),
        LIBS=shlex.join(libraries),
        CONFIG_SITE=str(PORT / "config/xos_config.site"),
        PYTHON_FOR_BUILD=str(build_python),
    )
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--build-python", type=Path)
    parser.add_argument(
        "--compile-probe",
        action="store_true",
        help="continue through make to expose the first target compile/link gap",
    )
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    sdk = args.sdk.resolve(strict=True)
    lock = json.loads((PORT / "source_lock.json").read_text())
    if sha256(archive) != lock["sha256"]:
        parser.error("CPython archive SHA-256 does not match source_lock.json")
    manifest = json.loads((sdk / "manifest.json").read_text())

    inputs = {
        "archive_sha256": lock["sha256"],
        "port": hash_tree(PORT),
        "script_sha256": sha256(__file__),
        "sdk": hash_tree(sdk),
    }
    fingerprint = hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode()
    ).hexdigest()[:20]
    work = ROOT / ".cache/xos_seed/cpython" / fingerprint
    work.mkdir(parents=True, exist_ok=True)
    source = work / "source"
    if not source.exists():
        extract_source(archive, source)
        apply_patches(source)

    expected = tuple(int(part) for part in lock["version"].split("."))
    build_python = ensure_build_python(
        source, work, expected, args.build_python
    )
    target_build = work / "target_build"
    target_build.mkdir(exist_ok=True)
    bridge = build_xos_bridge(work, sdk)
    configure_command = [
        str(source / "configure"),
        "--prefix=/usr",
        "--build=aarch64-apple-darwin27.0.0",
        "--host=x86_64-unknown-xos",
        f"--with-build-python={build_python}",
        "--without-ensurepip",
        "--disable-test-modules",
        "--without-mimalloc",
        "--without-readline",
        "--disable-ipv6",
    ]
    report = {
        "phase": "PY0a",
        "version": lock["version"],
        "target": lock["target"],
        "profile": lock["profile"],
        "fingerprint": fingerprint,
        "sdk_build_id": manifest.get("build_id"),
        "sdk_path": str(sdk),
        "build_python": str(build_python),
        "build_python_sha256": sha256(build_python),
        "configure_command": configure_command,
        "status": "configure_started",
        "guest_tested": False,
        "inputs": inputs,
    }
    report_path = work / "py0a_report.json"
    try:
        run(
            configure_command,
            cwd=target_build,
            env=target_environment(sdk, build_python, bridge),
            log=work / "target_configure.log",
        )
        report["status"] = "configured_not_built"
        if args.compile_probe:
            try:
                run(
                    ["make", "-j2"],
                    cwd=target_build,
                    env=target_environment(sdk, build_python, bridge),
                    log=work / "target_make.log",
                )
                report["status"] = "built_not_run"
            except subprocess.CalledProcessError as error:
                report["status"] = "compile_probe_failed"
                report["make_returncode"] = error.returncode
    except subprocess.CalledProcessError as error:
        report["status"] = "configure_failed"
        report["configure_returncode"] = error.returncode
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "inputs"}, indent=2))
    if report["status"] not in ("configured_not_built", "built_not_run"):
        log_name = (
            "target_make.log"
            if report["status"] == "compile_probe_failed"
            else "target_configure.log"
        )
        print(f"see {work / log_name}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
