# SPDX-License-Identifier: Apache-2.0
"""Build static XOS-hosted GNU Binutils tools from the locked 2.47 release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/binutils"
CACHE = ROOT / ".cache/xos_seed/binutils"
LOCK = json.loads((PORT / "source_lock.json").read_text())
TOOLS = ("as", "ld", "ar", "ranlib", "strip", "readelf", "objdump", "nm", "objcopy")
CONFIGURE_OPTIONS = (
    "--prefix=/usr",
    "--program-prefix=x86_64-elf-",
    "--disable-nls",
    "--disable-gdb",
    "--disable-sim",
    "--disable-gprofng",
    "--disable-gold",
    "--disable-plugins",
    "--disable-shared",
    "--disable-host-shared",
    "--disable-werror",
    "--without-system-zlib",
    "--with-system-readline",
    "--without-bzlib",
    "--without-lzma",
    "--with-zstd=no",
    "--without-debuginfod",
)
TARGET_FLAGS = (
    "-O2", "-g0", "-DXOS_NO_SYMLINKS", "-DXOS_NO_POSIX_FILE_MODES",
    "-DXOS_NO_UTIME", "-DXOS_NO_DLOPEN",
    "-mno-red-zone", "-fno-stack-protector", "-fno-pic",
    "-fno-pie", "-mcmodel=small", "-I",
)
TARGET_LINK_FLAGS = (
    "-nostdlib", "-static", "-no-pie",
    "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
    "-T", "<SDK>/user.ld", "<SDK>/crt0_posix.o", "-Wl,--start-group",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cache_seed_environment() -> dict[str, str]:
    """Read only the port's literal configure answers, never shell-evaluate them."""
    values: dict[str, str] = {}
    for raw in (PORT / "config/xos_cache_seed.sh").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./+-]+)", line)
        if match is None:
            raise RuntimeError(f"cache seed must contain only literal KEY=value entries: {line!r}")
        values[match.group(1)] = match.group(2)
    return values


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
        log: Path | None = None) -> str:
    print("+ " + " ".join(argv), flush=True)
    if log is None:
        result = subprocess.run(argv, cwd=cwd, env=env, check=True, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return result.stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as output:
        output.write("\n$ " + " ".join(argv) + "\n")
        output.flush()
        result = subprocess.run(argv, cwd=cwd, env=env, check=False, text=True,
                                stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        try:
            tail = log.read_text(errors="replace")[-12000:]
        except OSError:
            tail = ""
        raise RuntimeError(f"command failed ({result.returncode}); log={log}\n{tail}")
    return ""


def get_source() -> tuple[Path, str]:
    archive = CACHE / LOCK["source_archive"]
    CACHE.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        partial = archive.with_suffix(archive.suffix + ".part")
        print(f"Downloading {LOCK['source_url']}", flush=True)
        request = urllib.request.Request(LOCK["source_url"], headers={"User-Agent": "XOS-Binutils-Builder/1"})
        with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        actual = sha256(partial)
        if actual != LOCK["sha256"]:
            raise RuntimeError(f"source checksum mismatch: {actual}")
        os.replace(partial, archive)
    actual = sha256(archive)
    if actual != LOCK["sha256"]:
        raise RuntimeError(f"source checksum mismatch: expected {LOCK['sha256']}, got {actual}")
    source_root = CACHE / "source"
    source = source_root / f"binutils-{LOCK['version']}"
    if not source.is_dir():
        source_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive, "r:xz") as bundle:
            members = bundle.getmembers()
            if any(not (Path(member.name).parts and Path(member.name).parts[0] == source.name)
                   for member in members):
                raise RuntimeError("source archive has an unexpected top-level path")
            bundle.extractall(source_root, filter="data")
    version = (source / "bfd/version.m4").read_text(errors="replace")
    if "2.47" not in version:
        raise RuntimeError("extracted source does not identify itself as Binutils 2.47")
    return source, actual


def patch_records() -> list[dict[str, str]]:
    series = PORT / "patches/series"
    records = []
    for line in series.read_text().splitlines():
        patch_name = line.strip()
        if not patch_name or patch_name.startswith("#"):
            continue
        patch_path = PORT / "patches" / patch_name
        records.append({"file": str(patch_path.relative_to(PORT)), "sha256": sha256(patch_path)})
    return records


def patched_source(pristine: Path, destination: Path, patches: list[dict[str, str]]) -> Path:
    source = destination / "source"
    stamp = source / ".xos-patches.json"
    expected = json.dumps(patches, sort_keys=True)
    if stamp.is_file() and stamp.read_text() == expected:
        return source
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(pristine, source)
    patch_tool = shutil.which("patch")
    if patch_tool is None and patches:
        raise RuntimeError("the native patch utility is required to apply Binutils port patches")
    for record in patches:
        patch_path = PORT / record["file"]
        run([patch_tool, "-p1", "-i", str(patch_path)], cwd=source)
    stamp.write_text(expected)
    return source


def write_wrapper(path: Path, compiler: str, sdk: Path, libgcc: Path) -> None:
    payload = f'''#!/usr/bin/env python3
import os, sys
compiler = {compiler!r}
sdk = {str(sdk)!r}
libgcc = {str(libgcc)!r}
base = ["-DXOS_NO_SYMLINKS", "-DXOS_NO_POSIX_FILE_MODES", "-DXOS_NO_UTIME", "-DXOS_NO_DLOPEN", "-mno-red-zone", "-fno-stack-protector", "-fno-pic", "-fno-pie", "-mcmodel=small"]
args = sys.argv[1:]
compile_only = any(x in args for x in ("-c", "-S", "-E", "-M", "-MM", "-fsyntax-only"))
cmd = [compiler, *base]
if not compile_only:
    cmd += ["-nostdlib", "-static", "-no-pie", "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096", "-T", sdk + "/user.ld", sdk + "/crt0_posix.o"]
    cmd += ["-Wl,--start-group"]
cmd += args
cmd += ["-I", sdk + "/include"]
if not compile_only:
    cmd += [sdk + "/lib/libxos.a", sdk + "/lib/libxos_loader.a", "-L" + sdk + "/lib", "-lc", "-lm", libgcc, "-Wl,--end-group"]
os.execv(compiler, cmd)
'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    path.chmod(0o755)


def inspect_tools(install: Path, readelf: str) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for name in TOOLS:
        path = install / "usr/bin" / f"x86_64-elf-{name}"
        if not path.is_file():
            raise RuntimeError(f"required tool was not installed: {path}")
        header = run([readelf, "-h", str(path)])
        program_headers = run([readelf, "-l", str(path)])
        section_headers = run([readelf, "-S", str(path)])
        dynamic = run([readelf, "-d", str(path)])
        file_type = next((line for line in header.splitlines() if "Type:" in line), "")
        if ("ELF64" not in header or "Advanced Micro Devices X86-64" not in header
                or "EXEC" not in file_type):
            raise RuntimeError(f"wrong executable format for {path}:\n{header}")
        if "INTERP" in program_headers or "Dynamic section" in dynamic:
            raise RuntimeError(f"tool is dynamically linked: {path}")
        if (re.search(r"^\s*TLS\s", program_headers, re.MULTILINE)
                or re.search(r"^\s*\[\s*\d+\]\s+\.t(?:data|bss)\b",
                             section_headers, re.MULTILINE)):
            raise RuntimeError(f"tool requires unsupported thread-local storage: {path}")
        result[name] = {"path": str(path.relative_to(install)), "sha256": sha256(path),
                        "upstream_version": LOCK["version"]}
    return result


def build(sdk: Path, expected_sdk_hash: str, jobs: int) -> Path:
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
        raise RuntimeError("this locked build is configured for arm64 macOS")
    if len(expected_sdk_hash) != 64:
        raise RuntimeError("--expected-sdk-manifest-sha256 is required for a stable SDK handoff")
    sdk_manifest = sdk / "manifest.json"
    if not sdk_manifest.is_file():
        raise RuntimeError(f"SDK manifest is missing: {sdk_manifest}")
    actual_sdk_hash = sha256(sdk_manifest)
    if actual_sdk_hash != expected_sdk_hash:
        raise RuntimeError(f"SDK changed since handoff: expected {expected_sdk_hash}, got {actual_sdk_hash}")
    sdk_metadata = json.loads(sdk_manifest.read_text())
    if sdk_metadata.get("target") != "x86_64-elf":
        raise RuntimeError("SDK target must be x86_64-elf")
    required_sdk = ("crt0_posix.o", "user.ld", "include", "lib/libxos.a",
                    "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a")
    for item in required_sdk:
        if not (sdk / item).exists():
            raise RuntimeError(f"completed E08-2 SDK artifact is missing: {sdk / item}")
    sdk_inputs = {
        item: sha256(sdk / item)
        for item in ("crt0_posix.o", "user.ld", "lib/libxos.a",
                     "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a")
    }

    pristine_source, source_hash = get_source()
    patches = patch_records()
    bundled_components: dict[str, dict[str, object]] = {}
    for component, spec in LOCK.get("bundled_components", {}).items():
        header = pristine_source / spec["source_header"]
        notice = pristine_source / spec["source_notice"]
        source_license = pristine_source / "zlib/LICENSE"
        copied_license = PORT / spec["license_material"]
        match = re.search(rb'^#define ZLIB_VERSION "([^"]+)"', header.read_bytes(), re.MULTILINE)
        if match is None or match.group(1).decode() != spec["version"]:
            raise RuntimeError(f"unexpected bundled {component} version")
        if source_license.read_bytes() != copied_license.read_bytes():
            raise RuntimeError(f"copied bundled {component} license differs from upstream")
        bundled_components[component] = {
            "version": spec["version"],
            "source_archive_sha256": source_hash,
            "source_header": spec["source_header"],
            "source_header_sha256": sha256(header),
            "source_notice": spec["source_notice"],
            "source_notice_sha256": sha256(notice),
            "license_material": str(copied_license.relative_to(ROOT)),
            "license_sha256": sha256(copied_license),
            "external_library_dependency": False,
        }
    build_triple = run([str(pristine_source / "config.guess")]).strip()
    if not build_triple.startswith("aarch64-apple-darwin"):
        raise RuntimeError(f"unexpected GNU build triple: {build_triple}")
    host_triple = "x86_64-unknown-elf"
    target_triple = "x86_64-elf"
    canonical_host = run([str(pristine_source / "config.sub"), host_triple]).strip()
    canonical_target = run([str(pristine_source / "config.sub"), target_triple]).strip()
    if canonical_host != "x86_64-unknown-elf" or canonical_target != "x86_64-pc-elf":
        raise RuntimeError(f"unexpected canonical triples: {canonical_host}, {canonical_target}")

    compiler = shutil.which("x86_64-elf-gcc")
    if compiler is None:
        raise RuntimeError("x86_64-elf-gcc is required to generate the Seed programs")
    cxx_compiler = shutil.which("x86_64-elf-g++")
    if cxx_compiler is None:
        raise RuntimeError("x86_64-elf-g++ is required to generate the Seed programs")
    compiler_target = run([compiler, "-dumpmachine"]).strip()
    cxx_target = run([cxx_compiler, "-dumpmachine"]).strip()
    if compiler_target != "x86_64-elf" or cxx_target != compiler_target:
        raise RuntimeError(f"unexpected cross compiler targets: {compiler_target}, {cxx_target}")
    libgcc_path = Path(run([compiler, "-print-libgcc-file-name"]).strip()).resolve()
    if not libgcc_path.is_file():
        raise RuntimeError(f"cross compiler libgcc archive is missing: {libgcc_path}")
    gcc_version = run([compiler, "-dumpfullversion"]).strip()
    native_tools = {name: shutil.which(name) for name in ("make", "clang", "clang++")}
    object_tools = {name: shutil.which(f"x86_64-elf-{name}") for name in
                    ("ar", "as", "ld", "nm", "objcopy", "objdump", "ranlib",
                     "readelf", "strip")}
    if any(value is None for value in native_tools.values()):
        raise RuntimeError(f"missing native build tools: {native_tools}")
    if any(value is None for value in object_tools.values()):
        raise RuntimeError(f"missing x86_64-elf object tools: {object_tools}")
    cross_readelf = object_tools["readelf"]
    source_record = {
        "source_sha256": source_hash,
        "builder_sha256": sha256(Path(__file__)),
        "sdk_manifest_sha256": actual_sdk_hash,
        "sdk_inputs": sdk_inputs,
        "build": build_triple,
        "host": host_triple,
        "target": target_triple,
        "canonical_host": canonical_host,
        "canonical_target": canonical_target,
        "compiler": compiler,
        "compiler_target": compiler_target,
        "compiler_sha256": sha256(Path(compiler)),
        "gcc_version": gcc_version,
        "libgcc": {"path": str(libgcc_path), "sha256": sha256(libgcc_path)},
        "cxx_compiler": cxx_compiler,
        "cxx_compiler_target": cxx_target,
        "cxx_compiler_sha256": sha256(Path(cxx_compiler)),
        "configure_options": [f"--build={build_triple}", f"--host={host_triple}",
                              f"--target={target_triple}", *CONFIGURE_OPTIONS],
        "native_tools": {name: {"path": value, "sha256": sha256(Path(value)),
                                "version": run([value, "--version"]).splitlines()[0]}
                         for name, value in native_tools.items()},
        "target_tools": {name: {"path": value, "sha256": sha256(Path(value)),
                                "version": run([value, "--version"]).splitlines()[0]}
                         for name, value in object_tools.items()},
        "compile_flags": [*TARGET_FLAGS[:-1], "-I", str(sdk / "include")],
        "link_flags": [flag.replace("<SDK>", str(sdk)) for flag in TARGET_LINK_FLAGS],
        "runtime_libraries": [str(sdk / "lib/libxos.a"),
                              str(sdk / "lib/libxos_loader.a"), "-lc", "-lm",
                              str(libgcc_path)],
        "cache_seed_sha256": sha256(PORT / "config/xos_cache_seed.sh"),
        "patches": patches,
        "bundled_components": bundled_components,
    }
    fingerprint = hashlib.sha256(json.dumps(source_record, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
    work = CACHE / "build" / fingerprint
    work.mkdir(parents=True, exist_ok=True)
    source = patched_source(pristine_source, work, patches)
    build_dir = work / "build"
    install = work / "install"
    build_dir.mkdir(exist_ok=True)
    write_wrapper(work / "xos-cc", compiler, sdk, libgcc_path)
    write_wrapper(work / "xos-cxx", cxx_compiler, sdk, libgcc_path)
    cache_file = work / "xos.cache"
    if not cache_file.exists():
        shutil.copyfile(PORT / "config/xos_cache_seed.sh", cache_file)

    env = os.environ.copy()
    env.update({
        "CC": str(work / "xos-cc"),
        "CXX": str(work / "xos-cxx"),
        "CFLAGS": "-O2 -g0 -mno-red-zone -fno-stack-protector -fno-pic -fno-pie -mcmodel=small",
        "CXXFLAGS": "-O2 -g0 -mno-red-zone -fno-stack-protector -fno-pic -fno-pie -mcmodel=small",
        "LDFLAGS": "-static -no-pie",
        "CC_FOR_BUILD": native_tools["clang"],
        "CXX_FOR_BUILD": native_tools["clang++"],
        "CC_FOR_TARGET": compiler,
        "CXX_FOR_TARGET": cxx_compiler,
        "CFLAGS_FOR_BUILD": "-O2",
        "CXXFLAGS_FOR_BUILD": "-O2",
        "CPPFLAGS": "",
        "CPPFLAGS_FOR_BUILD": "",
        "LDFLAGS_FOR_BUILD": "",
        "LIBS": "",
        "AR": object_tools["ar"],
        "AR_FOR_TARGET": object_tools["ar"],
        "AS_FOR_TARGET": object_tools["as"],
        "LD_FOR_TARGET": object_tools["ld"],
        "RANLIB": object_tools["ranlib"],
        "RANLIB_FOR_TARGET": object_tools["ranlib"],
        "NM": object_tools["nm"],
        "NM_FOR_TARGET": object_tools["nm"],
        "STRIP": object_tools["strip"],
        "STRIP_FOR_TARGET": object_tools["strip"],
        "OBJCOPY_FOR_TARGET": object_tools["objcopy"],
        "OBJDUMP_FOR_TARGET": object_tools["objdump"],
        "READELF_FOR_TARGET": object_tools["readelf"],
        "MAKEINFO": "/usr/bin/true",
    })
    env.update(cache_seed_environment())
    configure = [str(source / "configure"), f"--build={build_triple}",
                 f"--host={host_triple}", f"--target={target_triple}", *CONFIGURE_OPTIONS]
    log = work / "build.log"
    if not (build_dir / "Makefile").exists():
        run(configure + [f"--cache-file={cache_file}"], cwd=build_dir, env=env, log=log)
    make = native_tools["make"]
    run([make, f"-j{jobs}", "all-gas", "all-ld", "all-binutils"],
        cwd=build_dir, env=env, log=log)
    install.mkdir(parents=True, exist_ok=True)
    run([make, "install-gas", "install-ld", "install-binutils", f"DESTDIR={install}"],
        cwd=build_dir, env=env, log=log)
    tools = inspect_tools(install, cross_readelf)

    licenses = {}
    for name in ("COPYING", "COPYING.LIB", "COPYING3", "COPYING3.LIB", "zlib-LICENSE"):
        license_path = PORT / "upstream" / name
        licenses[str(license_path.relative_to(ROOT))] = sha256(license_path)
    manifest = {
        **source_record,
        "canonical": {"build": build_triple, "host": canonical_host, "target": canonical_target},
        "sdk_manifest": str(sdk_manifest.relative_to(ROOT)),
        "sdk_input_hashes": sdk_inputs,
        "tools": tools,
        "licenses": licenses,
        "configure_log": str(log.relative_to(ROOT)),
        "manifest_schema": 1,
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(work)
    return work


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=ROOT / "build/sdk")
    parser.add_argument("--expected-sdk-manifest-sha256", required=True)
    parser.add_argument("--jobs", type=int, default=max(1, os.cpu_count() or 1))
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        build(args.sdk.resolve(), args.expected_sdk_manifest_sha256, args.jobs)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"binutils build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
