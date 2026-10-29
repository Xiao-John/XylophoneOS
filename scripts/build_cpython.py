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


def target_environment(sdk, build_python, bridge, zlib_prefix=None):
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
    manifest = json.loads((sdk / "manifest.json").read_text())
    threaded = manifest.get("thread_abi") == 1
    if threaded:
        cflags.extend(["-DXOS_THREADED_RUNTIME", "-ftls-model=local-exec"])
    # LDFLAGS is duplicated into PY_LDFLAGS by CPython's Makefile, and GNU ld
    # rejects the same linker script twice. Keep -L/-T/crt0 in LIBS instead,
    # where they appear exactly once.
    ldflags = [
        "-nostdlib",
        "-static",
        "-no-pie",
        "-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
    ]
    sdk_libraries = [
        str(sdk / "lib/libxos.a"),
    ]
    if zlib_prefix is not None:
        zlib_prefix = Path(zlib_prefix).resolve(strict=True)
        if not (zlib_prefix / "include/zlib.h").is_file():
            raise FileNotFoundError(f"missing zlib.h under {zlib_prefix}")
        if not (zlib_prefix / "include/zconf.h").is_file():
            raise FileNotFoundError(f"missing zconf.h under {zlib_prefix}")
        if not (zlib_prefix / "lib/libz.a").is_file():
            raise FileNotFoundError(f"missing static libz.a under {zlib_prefix}")
        ldflags.extend(["-L", str(zlib_prefix / "lib")])
    cppflags = ["-D__xos__=1", "-isystem", str(sdk / "include")]
    if zlib_prefix is not None:
        cppflags.extend(["-isystem", str(zlib_prefix / "include")])
    loader_archive = sdk / "lib/libxos_loader.a"
    if loader_archive.exists():
        sdk_libraries.append(str(loader_archive))
    target_libgcc = sdk / "cpp/lib/libgcc.a"
    threaded_runtime_libraries = []
    if threaded:
        threaded_runtime_libraries = [
            str(sdk / "cpp/lib/libstdc++.a"),
            str(sdk / "cpp/lib/libsupc++.a"),
        ]
    libraries = [
        "-L",
        str(sdk / "lib"),
        "-T",
        str(sdk / "user.ld"),
        str(sdk / "crt0_posix.o"),
        str(bridge),
        "-Wl,--start-group",
        *sdk_libraries,
        *( ["-lz"] if zlib_prefix is not None else [] ),
        *threaded_runtime_libraries,
        str(sdk / "lib/libc.a"),
        str(sdk / "lib/libm.a"),
        str(target_libgcc) if target_libgcc.exists() else libgcc,
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
            cppflags
        ),
        LDFLAGS=shlex.join(ldflags),
        LIBS=shlex.join(libraries),
        CONFIG_SITE=str(PORT / "config/xos_config.site"),
        PYTHON_FOR_BUILD=str(build_python),
    )
    return env


def prepare_pillow(archive, source, zlib_prefix):
    """Select the upstream core sources without rewriting PIL or its codecs."""
    if zlib_prefix is None:
        raise ValueError("static Pillow core requires the verified zlib prefix")
    lock = json.loads((PORT / "pillow/source_lock.json").read_text())
    if sha256(archive) != lock["sha256"]:
        raise ValueError("Pillow archive SHA-256 does not match source_lock.json")
    pillow = source / "Modules/xos_pillow"
    if not pillow.exists():
        extract_source(archive, pillow)
    for name, expected in lock["source_hashes"].items():
        if sha256(pillow / name) != expected:
            raise ValueError(f"modified Pillow input: {name}")
    sources = ["xos_pillow/" + name for name in lock["sources"]]
    include = pillow / "src/libImaging"
    configuration = source / "Modules/xos_pillow_config.h"
    configuration.write_text('// SPDX-License-Identifier: Apache-2.0\n'
                             '#define PILLOW_VERSION "' + lock["version"] + '"\n'
                             '#define HAVE_LIBZ 1\n')
    flags = f'PILLOW_CFLAGS=-include {configuration}'
    entry = flags + "\n" + " ".join(["_imaging", *sources, f"-I{include}",
                      f"-I{zlib_prefix / 'include'}",
                      '$(PILLOW_CFLAGS)',
                      f"-L{zlib_prefix / 'lib'}", "-lz"])
    # CPython's makesetup only accepts a C identifier as the Setup module name.
    # The package imports PIL._imaging, so keep the upstream init symbol and
    # add its qualified name to the generated inittab through config.c.in.
    template = source / "Modules/config.c.in"
    text = template.read_text()
    marker = '    {"PIL._imaging", PyInit__imaging},'
    if marker not in text:
        text = text.replace("/* -- ADDMODULE MARKER 2 -- */",
                            "/* -- ADDMODULE MARKER 2 -- */\n" + marker)
        template.write_text(text)
    return entry, lock


def write_setup_local(source, sqlite_prefix, compression_prefixes, pillow_entry=None):
    entries = ["# Generated by scripts/build_cpython.py from pinned PY3 receipts."]
    if pillow_entry:
        entries.append(pillow_entry)
    if compression_prefixes:
        if set(compression_prefixes) != {"bzip2", "xz", "zstd"}:
            raise ValueError("B4 integration requires bzip2, xz, and zstd prefixes")
        hooks = {
            "bzip2": f"_bz2 _bz2module.c -I{compression_prefixes['bzip2'] / 'include'} -L{compression_prefixes['bzip2'] / 'lib'} -lbz2",
            "xz": f"_lzma _lzmamodule.c -I{compression_prefixes['xz'] / 'include'} -L{compression_prefixes['xz'] / 'lib'} -llzma",
            "zstd": f"_zstd _zstd/_zstdmodule.c _zstd/zstddict.c _zstd/compressor.c _zstd/decompressor.c -I{compression_prefixes['zstd'] / 'include'} -L{compression_prefixes['zstd'] / 'lib'} -lzstd",
        }
        entries.extend(hooks[name] for name in ("bzip2", "xz", "zstd"))
    if sqlite_prefix is not None:
        entries.append(
            f"_sqlite3 _sqlite/blob.c _sqlite/connection.c _sqlite/cursor.c "
            f"_sqlite/microprotocols.c _sqlite/module.c _sqlite/prepare_protocol.c "
            f"_sqlite/row.c _sqlite/statement.c _sqlite/util.c "
            f"-I{sqlite_prefix / 'include'} -L{sqlite_prefix / 'lib'} -lsqlite3"
        )
    path = Path(source) / "Modules/Setup.local"
    path.write_text("\n".join(entries) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--build-python", type=Path)
    parser.add_argument(
        "--zlib-prefix",
        type=Path,
        help="prefix produced by build_cpython_zlib.py; enables static zlib",
    )
    parser.add_argument("--sqlite-prefix", type=Path,
                        help="prefix produced by build_cpython_sqlite.py")
    parser.add_argument("--compression-report", type=Path,
                        help="report produced by build_cpython_compression.py")
    parser.add_argument("--pillow-archive", type=Path,
                        help="locked Pillow source archive; static core and zlib only")
    parser.add_argument(
        "--compile-probe",
        action="store_true",
        help="continue through make to expose the first target compile/link gap",
    )
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    pillow_archive = args.pillow_archive.resolve(strict=True) if args.pillow_archive else None
    sdk = args.sdk.resolve(strict=True)
    lock = json.loads((PORT / "source_lock.json").read_text())
    if sha256(archive) != lock["sha256"]:
        parser.error("CPython archive SHA-256 does not match source_lock.json")
    manifest = json.loads((sdk / "manifest.json").read_text())
    threaded = manifest.get("thread_abi") == 1
    zlib_prefix = args.zlib_prefix.resolve(strict=True) if args.zlib_prefix else None
    sqlite_prefix = args.sqlite_prefix.resolve(strict=True) if args.sqlite_prefix else None
    compression_report_path = args.compression_report.resolve(strict=True) if args.compression_report else None
    zlib_report = None
    if zlib_prefix is not None:
        zlib_report_path = zlib_prefix.parent / "report.json"
        zlib_report = json.loads(zlib_report_path.read_text())
        if zlib_report.get("status") != "built":
            parser.error("zlib build report is not successful")
        if zlib_report.get("prefix") != str(zlib_prefix):
            parser.error("zlib prefix does not match its build report")

    sqlite_report = None
    if sqlite_prefix is not None:
        sqlite_report_path = sqlite_prefix.parent / "receipt.json"
        sqlite_report = json.loads(sqlite_report_path.read_text())
        if sqlite_report.get("status") != "built" or sqlite_report.get("prefix") != str(sqlite_prefix):
            parser.error("SQLite prefix does not match a successful receipt")
        if not (sqlite_prefix / "include/sqlite3.h").is_file() or not (sqlite_prefix / "lib/libsqlite3.a").is_file():
            parser.error("SQLite prefix is incomplete")

    compression_report = None
    compression_prefixes = {}
    if compression_report_path is not None:
        compression_report = json.loads(compression_report_path.read_text())
        if compression_report.get("status") != "built":
            parser.error("compression report is not successful")
        for name, component in compression_report.get("components", {}).items():
            prefix = Path(component["prefix"]).resolve(strict=True)
            if component.get("status") != "built":
                parser.error(f"compression component {name} is not built")
            compression_prefixes[name] = prefix

    inputs = {
        "archive_sha256": lock["sha256"],
        "port": hash_tree(PORT),
        "script_sha256": sha256(__file__),
        "sdk": hash_tree(sdk),
        "zlib_report_sha256": (
            sha256(zlib_prefix.parent / "report.json") if zlib_prefix is not None else None
        ),
        "sqlite_report_sha256": sha256(sqlite_prefix.parent / "receipt.json") if sqlite_prefix is not None else None,
        "compression_report_sha256": sha256(compression_report_path) if compression_report_path is not None else None,
        "pillow_archive_sha256": sha256(pillow_archive) if pillow_archive else None,
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
    pillow_entry, pillow_lock = prepare_pillow(pillow_archive, source, zlib_prefix) if pillow_archive else (None, None)
    setup_local = write_setup_local(source, sqlite_prefix, compression_prefixes, pillow_entry)

    expected = tuple(int(part) for part in lock["version"].split("."))
    build_python = ensure_build_python(
        source, work, expected, args.build_python
    )
    target_build = work / "target_build"
    target_build.mkdir(exist_ok=True)
    if pillow_lock:
        for filename in pillow_lock["sources"]:
            (target_build / "Modules/xos_pillow" / Path(filename).parent).mkdir(parents=True, exist_ok=True)
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
        "profile": (
            "py_t3_static_gil_pthread"
            if threaded
            else lock["profile"]
        ),
        "fingerprint": fingerprint,
        "sdk_build_id": manifest.get("build_id"),
        "sdk_profile": manifest.get("profile"),
        "sdk_manifest_sha256": sha256(sdk / "manifest.json"),
        "sdk_path": str(sdk),
        "zlib_prefix": str(zlib_prefix) if zlib_prefix is not None else None,
        "zlib_report_sha256": inputs["zlib_report_sha256"],
        "sqlite_prefix": str(sqlite_prefix) if sqlite_prefix is not None else None,
        "sqlite_report_sha256": inputs["sqlite_report_sha256"],
        "compression_report": str(compression_report_path) if compression_report_path else None,
        "compression_report_sha256": inputs["compression_report_sha256"],
        "setup_local_sha256": sha256(setup_local),
        "static_extensions": [
            *( ["zlib"] if zlib_prefix else [] ),
            *( ["_sqlite3"] if sqlite_prefix else [] ),
            *( ["_bz2", "_lzma", "_zstd"] if compression_prefixes else [] ),
            *( ["PIL._imaging"] if pillow_archive else [] ),
        ],
        "pillow": pillow_lock,
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
            env=target_environment(sdk, build_python, bridge, zlib_prefix),
            log=work / "target_configure.log",
        )
        target_setup = target_build / "Modules/Setup.local"
        target_setup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(setup_local, target_setup)
        run(
            [
                str(source / "Modules/makesetup"),
                "-c", str(source / "Modules/config.c.in"),
                "-s", "Modules",
                "Modules/Setup.local",
                "Modules/Setup.stdlib",
                "Modules/Setup.bootstrap",
                str(source / "Modules/Setup"),
            ],
            cwd=target_build,
            env=target_environment(sdk, build_python, bridge, zlib_prefix),
            log=work / "target_setup.log",
        )
        os.replace(target_build / "config.c", target_build / "Modules/config.c")
        report["generated_config_sha256"] = sha256(target_build / "Modules/config.c")
        if pillow_archive:
            generated = (target_build / "Modules/config.c").read_text()
            if generated.count('{"PIL._imaging", PyInit__imaging}') != 1:
                raise ValueError("Pillow qualified builtin registration is missing or duplicated")
        report["status"] = "configured_not_built"
        if args.compile_probe:
            try:
                run(
                    ["make", "-j2"],
                    cwd=target_build,
                    env=target_environment(sdk, build_python, bridge, zlib_prefix),
                    log=work / "target_make.log",
                )
                report["status"] = "built_not_run"
                executable = target_build / "python.exe"
                report["executable"] = {"path": str(executable),
                                        "bytes": executable.stat().st_size,
                                        "sha256": sha256(executable)}
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
