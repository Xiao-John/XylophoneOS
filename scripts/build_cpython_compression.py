# SPDX-License-Identifier: Apache-2.0
"""Build isolated static CPython compression dependencies for the XOS target.

This prepares libbz2, liblzma, and libzstd prefixes only. It does not edit the
CPython configuration. The integration hooks in compression_lock.json are for
the central CPython builder to consume after the prefixes have been accepted.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/cpython/compression"
CACHE = ROOT / ".cache/xos_seed/cpython/compression"
DEFAULT_SDK = ROOT / "build/threading_sdk"
COMPONENTS = ("bzip2", "xz", "zstd")
BASE_CFLAGS = [
    "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic",
    "-fno-stack-protector", "-ffunction-sections", "-fdata-sections",
    "-D__xos__=1",
]


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
    return str(Path(value).resolve())


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


def extract_source(archive, destination, expected_root, include_prefixes=None):
    destination.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        roots = {Path(member.name).parts[0] for member in members if member.name}
        if roots != {expected_root}:
            raise ValueError(f"unexpected archive roots: {sorted(roots)}")
        for member in members:
            path = Path(member.name)
            parts = path.parts
            if not parts or path.is_absolute() or ".." in parts:
                raise ValueError(f"unsafe archive member: {member.name}")
            relative = parts[1:]
            if not relative:
                continue
            if include_prefixes and relative[0] not in include_prefixes:
                continue
            if member.issym() or member.islnk():
                raise ValueError(f"archive link not admitted: {member.name}")
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


def copy_headers(source, include, component):
    include.mkdir(parents=True, exist_ok=True)
    if component["name"] == "bzip2":
        shutil.copyfile(source / "bzlib.h", include / "bzlib.h")
    elif component["name"] == "xz":
        api = source / "src/liblzma/api"
        shutil.copyfile(api / "lzma.h", include / "lzma.h")
        shutil.copytree(api / "lzma", include / "lzma", dirs_exist_ok=True)
    else:
        lib_include = source / "lib"
        for header in component["header_files"]:
            shutil.copyfile(lib_include / header, include / header)


def validate_static_library(ar, library):
    members = subprocess.check_output([ar, "t", str(library)], text=True).splitlines()
    if len(members) < 2 or library.stat().st_size < 4096:
        raise ValueError(f"static archive is unexpectedly small: {library}")
    return members


def build_component(component, archive, work, sdk, tools, env):
    name = component["name"]
    source = work / f"source_{name}"
    build = work / f"target_build_{name}"
    prefix = work / "prefix" / name
    build.mkdir()
    extract_source(
        archive, source, component["archive_root"],
        include_prefixes=("lib",) if name == "zstd" else None,
    )
    local_env = dict(env)
    local_env["CFLAGS"] = " ".join(BASE_CFLAGS + ["-isystem", str(sdk / "include")])
    library = prefix / "lib" / component["library"]
    if name == "bzip2":
        run(
            ["make", "-j2", "CC=" + tools["cc"], "AR=" + tools["ar"],
             "RANLIB=" + tools["ranlib"], "CFLAGS=" + local_env["CFLAGS"],
             "ARFLAGS=rc", "libbz2.a"],
            cwd=source, env=local_env, log=work / "bzip2_make.log",
        )
        library.parent.mkdir(parents=True)
        shutil.copyfile(source / "libbz2.a", library)
    elif name == "xz":
        configure_env = dict(local_env)
        configure_env.update(CC=tools["cc"], AR=tools["ar"], RANLIB=tools["ranlib"])
        target_libgcc = sdk / "cpp/lib/libgcc.a"
        configure_env["LDFLAGS"] = " ".join([
            "-nostdlib", "-static", "-no-pie", "-L" + str(sdk / "lib"),
            "-T" + str(sdk / "user.ld"), "-Wl,--gc-sections,--build-id=none",
        ])
        sdk_threaded = json.loads((sdk / "manifest.json").read_text()).get("thread_abi") == 1
        configure_env["LIBS"] = " ".join([
            str(sdk / "crt0_posix.o"), "-Wl,--start-group",
            str(sdk / "lib/libxos.a"), str(sdk / "lib/libc.a"),
            str(sdk / "lib/libm.a"),
            *([str(sdk / "cpp/lib/libstdc++.a"), str(sdk / "cpp/lib/libsupc++.a")]
              if sdk_threaded else []),
            str(target_libgcc) if target_libgcc.exists() else "-lgcc",
            "-Wl,--end-group",
        ])
        run(
            ["/bin/sh", str(source / "configure"), "--host=x86_64-elf",
             "--disable-shared", "--enable-static", "--disable-doc",
             "--disable-nls", "--disable-threads", f"--prefix={prefix}"],
            cwd=build, env=configure_env, log=work / "xz_configure.log",
        )
        run(
            ["make", "-j2", "-C", str(build / "src/liblzma"),
             "LIBS=", "LDFLAGS=", "liblzma.la"],
            cwd=build, env=configure_env, log=work / "xz_make.log",
        )
        built_library = build / "src/liblzma/.libs/liblzma.a"
        if not built_library.is_file():
            raise FileNotFoundError(f"liblzma archive missing: {built_library}")
        library.parent.mkdir(parents=True)
        shutil.copyfile(built_library, library)
    else:
        zstd_env = dict(local_env)
        zstd_env.update(CC=tools["cc"], AR=tools["ar"], RANLIB=tools["ranlib"])
        zstd_build = build / "zstd_objects"
        run(
            ["make", "-j2", "-C", str(source / "lib"), "libzstd.a",
             "CC=" + tools["cc"], "AR=" + tools["ar"],
             "RANLIB=" + tools["ranlib"], "CFLAGS=" + zstd_env["CFLAGS"],
             "BUILD_DIR=" + str(zstd_build), "CPPFLAGS="],
            cwd=build, env=zstd_env, log=work / "zstd_make.log",
        )
        built_library = source / "lib/libzstd.a"
        if not built_library.is_file():
            raise FileNotFoundError(f"libzstd archive missing: {built_library}")
        library.parent.mkdir(parents=True)
        shutil.copyfile(built_library, library)

    include = prefix / "include"
    copy_headers(source, include, component)
    members = validate_static_library(tools["ar"], library)
    return {
        "prefix": str(prefix),
        "include": str(include),
        "library": str(library),
        "library_sha256": sha256(library),
        "library_bytes": library.stat().st_size,
        "library_members": members,
        "header_sha256": {
            path.relative_to(include).as_posix(): sha256(path)
            for path in sorted(include.rglob("*")) if path.is_file()
        },
        "threading": "disabled" if name in ("xz", "zstd") else "not used",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--archive-dir", type=Path, default=CACHE / "sources")
    parser.add_argument("--only", choices=COMPONENTS, action="append")
    args = parser.parse_args()
    sdk = args.sdk.resolve(strict=True)
    archive_dir = args.archive_dir.resolve(strict=True)
    lock_path = PORT / "compression_lock.json"
    lock = json.loads(lock_path.read_text())
    components = [item for item in lock["components"] if not args.only or item["name"] in args.only]
    if not components:
        parser.error("no compression components selected")
    for component in lock["components"]:
        actual_license = sha256(PORT / component["license_file"])
        if actual_license != component["license_sha256"]:
            parser.error(f"{component['name']} license hash does not match compression_lock.json")
    archives = {}
    for component in components:
        archive = archive_dir / component["archive"]
        if not archive.is_file():
            parser.error(f"missing source archive: {archive}")
        actual = sha256(archive)
        if actual != component["archive_sha256"]:
            parser.error(f"{component['name']} source archive hash does not match compression_lock.json")
        archives[component["name"]] = archive

    tools = {
        "cc": os.environ.get("XOS_CC") or executable("x86_64-elf-gcc"),
        "ar": os.environ.get("XOS_AR") or executable("x86_64-elf-ar"),
        "ranlib": os.environ.get("XOS_RANLIB") or executable("x86_64-elf-ranlib"),
    }
    sdk_manifest = sdk / "manifest.json"
    if not sdk_manifest.is_file():
        parser.error(f"SDK receipt is missing: {sdk_manifest}")
    inputs = {
        "archives": {name: sha256(path) for name, path in sorted(archives.items())},
        "build_script_sha256": sha256(__file__),
        "lock_sha256": sha256(lock_path),
        "sdk_manifest_sha256": sha256(sdk_manifest),
        "tools": {name: {"path": path, "sha256": sha256(path)} for name, path in tools.items()},
        "components": [item["name"] for item in components],
    }
    fingerprint = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:20]
    work = CACHE / fingerprint
    if work.exists():
        receipt = work / "report.json"
        if receipt.is_file():
            report = json.loads(receipt.read_text())
            if report.get("status") == "built" and report.get("fingerprint") == fingerprint:
                print(json.dumps(report, indent=2, sort_keys=True))
                return
        raise FileExistsError(f"partial compression work directory exists; inspect it: {work}")
    work.mkdir(parents=True)
    env = dict(os.environ)
    report = {
        "phase": "PY3-B4-compression",
        "status": "build_started",
        "fingerprint": fingerprint,
        "inputs": inputs,
        "sdk_path": str(sdk),
        "sdk_manifest_sha256": inputs["sdk_manifest_sha256"],
        "integration_hooks": lock["cpython_integration"]["setup_entries"],
        "components": {},
    }
    try:
        for component in components:
            result = build_component(component, archives[component["name"]], work, sdk, tools, env)
            result.update({
                "status": "built",
                "fingerprint": fingerprint,
                "version": component["version"],
                "source_url": component["source_url"],
                "source_archive_sha256": component["archive_sha256"],
                "license_id": component["license_id"],
                "license_file": str(PORT / component["license_file"]),
                "license_sha256": component["license_sha256"],
            })
            (Path(result["prefix"]) / "receipt.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n"
            )
            report["components"][component["name"]] = result
        report["status"] = "built"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise
    (work / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
