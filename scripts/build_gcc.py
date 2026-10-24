# SPDX-License-Identifier: Apache-2.0
"""Build the XOS-hosted GCC C Seed from the locked GCC 16.2.0 release."""
from __future__ import annotations
import argparse, hashlib, json, os, platform, shutil, subprocess, sys, tarfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "src/ports/gcc"
CACHE = ROOT / ".cache/xos_seed/gcc"
LOCK = json.loads((PORT / "source_lock.json").read_text()) if (PORT / "source_lock.json").is_file() else {}
CONFIGURE_OPTIONS = (
    "--prefix=/usr", "--disable-nls", "--disable-werror",
    "--disable-bootstrap", "--disable-multilib", "--disable-shared",
    "--disable-host-shared", "--disable-threads", "--enable-static",
    "--enable-languages=c", "--with-newlib", "--without-isl",
    "--disable-libssp", "--disable-libquadmath", "--disable-libgomp",
    "--disable-libatomic", "--disable-libsanitizer", "--disable-libvtv",
    "--disable-libstdcxx", "--disable-lto",
)

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def sha512(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def run(argv, *, cwd=None, env=None, log=None):
    print("+ " + " ".join(map(str, argv)), flush=True)
    if log is None:
        r = subprocess.run(argv, cwd=cwd, env=env, check=True, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return r.stdout
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as out:
        out.write("\n$ " + " ".join(map(str, argv)) + "\n")
        out.flush()
        r = subprocess.run(argv, cwd=cwd, env=env, check=False, text=True,
                           stdout=out, stderr=subprocess.STDOUT)
    if r.returncode:
        try: tail = log.read_text(errors="replace")[-12000:]
        except OSError: tail = ""
        raise RuntimeError(f"command failed ({r.returncode}); log={log}\n{tail}")
    return ""

def download(url: str, path: Path, expected: str, digest="sha256"):
    if path.is_file():
        actual = sha256(path) if digest == "sha256" else sha512(path)
        if actual == expected: return
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    print(f"Downloading {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "XOS-GCC-Builder/1"})
    with urllib.request.urlopen(req, timeout=120) as src, part.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    actual = sha256(part) if digest == "sha256" else sha512(part)
    if actual != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {url}: {actual}")
    os.replace(part, path)

def apply_patches(source: Path):
    """Apply the locked C-only port patches once to the private source tree."""
    marker = source / "configure"
    if "libcody" not in marker.read_text(errors="replace"):
        return
    patches = sorted((PORT / "patches").glob("*.patch"))
    if not patches:
        raise RuntimeError("C-only host-lib patch is missing")
    for patch in patches:
        run(["patch", "-p1", "-N", "-d", str(source), "-i", str(patch)])

def source_tree() -> Path:
    if not LOCK: raise RuntimeError("src/ports/gcc/source_lock.json is missing")
    tar = CACHE / LOCK["source_archive"]
    download(LOCK["source_url"], tar, LOCK["sha256"])
    root = CACHE / "source"
    source = root / f"gcc-{LOCK['version']}"
    if not source.is_dir():
        root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tar, "r:xz") as bundle:
            names = bundle.getmembers()
            top = source.name
            if any(not (m.name == top or m.name.startswith(top + "/")) for m in names):
                raise RuntimeError("GCC source archive has an unexpected top-level path")
            bundle.extractall(root, filter="data")
    apply_patches(source)
    return source

def dependency_tree(source: Path, name: str, spec: dict) -> Path:
    target = source / name
    if target.is_dir(): return target
    archive = CACHE / spec["archive"]
    download(spec["url"], archive, spec["sha512"], "sha512")
    tmp = CACHE / ("dep-" + name)
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with tarfile.open(archive, "r:*") as bundle:
        members = bundle.getmembers()
        root = spec['package']
        if any(not (m.name == root or m.name.startswith(root + "/")) for m in members):
            raise RuntimeError(f"unexpected top-level path in {archive}")
        bundle.extractall(tmp, filter="data")
    shutil.move(str(tmp / spec["package"]), str(target))
    shutil.rmtree(tmp, ignore_errors=True)
    return target

def wrapper(path: Path, compiler: str, sdk: Path, libgcc: Path, cxx_runtime: Path | None = None,
            stdcxx: Path | None = None):
    cxx_literal = repr(str(cxx_runtime)) if cxx_runtime is not None else "None"
    stdcxx_literal = repr(str(stdcxx)) if stdcxx is not None else "None"
    payload = f'''#!/usr/bin/env python3
import os, sys
compiler = {compiler!r}
sdk = {str(sdk)!r}
libgcc = {str(libgcc)!r}
cxx_runtime = {cxx_literal}
stdcxx = {stdcxx_literal}
base = ["-DXOS_NO_SYMLINKS", "-DXOS_NO_UNIX_SOCKETS", "-DXOS_NO_POSIX_FILE_MODES", "-DXOS_NO_UTIME", "-DXOS_NO_DLOPEN", "-mno-red-zone", "-fno-stack-protector", "-fno-pic", "-fno-pie", "-mcmodel=small"]
args = sys.argv[1:]
compile_only = any(x in args for x in ("-c", "-S", "-E", "-M", "-MM", "-fsyntax-only"))
cmd = [compiler, *base]
if cxx_runtime is not None:
    cmd += ["-I", {str(PORT / "include")!r}, "-include", "xos_dirent_compat.h"]
if stdcxx is not None:
    cmd += ["-I", stdcxx + "/include/c++/16.2.0",
            "-I", stdcxx + "/include/c++/16.2.0/x86_64-unknown-elf",
            "-I", stdcxx + "/include/c++/16.2.0/backward"]
if not compile_only:
    cmd += ["-nostdlib", "-static", "-no-pie", "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096", "-T", sdk + "/user.ld", sdk + "/crt0_posix.o", "-Wl,--start-group"]
cmd += args
cmd += ["-I", sdk + "/include"]
if not compile_only:
    cmd += [sdk + "/lib/libxos.a", sdk + "/lib/libxos_loader.a", "-L" + sdk + "/lib", "-lc", "-lm", libgcc]
    if stdcxx is not None:
        cmd += [stdcxx + "/lib/libstdc++.a"]
    if cxx_runtime is not None:
        cmd += [str(cxx_runtime)]
    cmd += ["-Wl,--end-group"]
os.execv(compiler, cmd)
'''
    path.write_text(payload); path.chmod(0o755)

def inspect_gcc(install: Path, readelf: str):
    result = {}
    for name in ("gcc", "cc1", "collect2"):
        path = install / "usr/bin" / name
        if name != "gcc": path = install / "usr/libexec/gcc/x86_64-elf" / LOCK["version"] / name
        if not path.is_file():
            result[name] = {"present": False}; continue
        header = run([readelf, "-h", str(path)])
        dynamic = run([readelf, "-d", str(path)])
        if "ELF64" not in header or "Advanced Micro Devices X86-64" not in header or "EXEC" not in header:
            raise RuntimeError(f"not a static x86_64 ELF: {path}")
        if "INTERP" in run([readelf, "-l", str(path)]) or "Dynamic section" in dynamic:
            raise RuntimeError(f"dynamic GCC Seed artifact: {path}")
        result[name] = {"path": str(path.relative_to(install)), "sha256": sha256(path), "bytes": path.stat().st_size}
    if not result.get("gcc", {}).get("sha256"):
        raise RuntimeError("gcc driver was not installed")
    return result

def build(sdk: Path, expected: str, jobs: int, configure_only: bool, stdcxx: Path):
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
        raise RuntimeError("this lock targets arm64 macOS")
    manifest = sdk / "manifest.json"
    if not manifest.is_file(): raise RuntimeError(f"SDK manifest missing: {manifest}")
    actual = sha256(manifest)
    if actual != expected: raise RuntimeError(f"SDK changed: expected {expected}, got {actual}")
    meta = json.loads(manifest.read_text())
    if meta.get("target") != "x86_64-elf": raise RuntimeError("SDK target must be x86_64-elf")
    for item in ("crt0_posix.o", "user.ld", "include", "lib/libxos.a", "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a"):
        if not (sdk / item).exists(): raise RuntimeError(f"missing SDK artifact: {item}")
    gcc = shutil.which("x86_64-elf-gcc"); gxx = shutil.which("x86_64-elf-g++")
    if not gcc or not gxx: raise RuntimeError("x86_64-elf-gcc/g++ required")
    if run([gcc, "-dumpmachine"]).strip() != "x86_64-elf": raise RuntimeError("wrong cross target")
    libgcc = Path(run([gcc, "-print-libgcc-file-name"]).strip())
    if not libgcc.is_file(): raise RuntimeError(f"libgcc missing: {libgcc}")
    native = {n: shutil.which(n) for n in ("make", "clang", "clang++")}
    if any(v is None for v in native.values()): raise RuntimeError(f"missing build tools: {native}")
    obj = {n: shutil.which("x86_64-elf-" + n) for n in ("ar", "as", "ld", "nm", "objcopy", "objdump", "ranlib", "readelf", "strip")}
    if any(v is None for v in obj.values()): raise RuntimeError(f"missing target binutils: {obj}")
    source = source_tree()
    deps = LOCK.get("dependencies", {})
    for name, spec in deps.items(): dependency_tree(source, name, spec)
    sdk_inputs = {item: sha256(sdk / item) for item in ("crt0_posix.o", "user.ld", "lib/libxos.a", "lib/libxos_loader.a", "lib/libc.a", "lib/libm.a")}
    build_triple = run([str(source / "config.guess")]).strip()
    host = "x86_64-unknown-elf"; target = "x86_64-elf"
    stdcxx = stdcxx.resolve()
    cxx_config = stdcxx / "include/c++/16.2.0/bits/c++config.h"
    if not cxx_config.is_file():
        cxx_config = stdcxx / "include/c++/16.2.0/x86_64-unknown-elf/bits/c++config.h"
    if not cxx_config.is_file() or not (stdcxx / "lib/libstdc++.a").is_file():
        raise RuntimeError(f"host libstdc++ prefix is incomplete: {stdcxx}")
    patch_files = sorted((PORT / "patches").glob("*.patch"))
    record = {"source_sha256": sha256(CACHE / LOCK["source_archive"]), "sdk_manifest_sha256": actual,
              "patches": {p.name: sha256(p) for p in patch_files},
              "config_site_sha256": sha256(PORT / "config/xos_cache_seed.sh"),
              "cxx_runtime_sha256": sha256(PORT / "cxx_runtime.cpp"),
              "cxx_new_header_sha256": sha256(PORT / "include/new"),
              "stdcxx_manifest": str(stdcxx),
              "sdk_inputs": sdk_inputs, "build": build_triple, "host": host, "target": target,
              "configure_options": [f"--build={build_triple}", f"--host={host}", f"--target={target}", *CONFIGURE_OPTIONS],
              "compiler": str(gcc), "compiler_sha256": sha256(Path(gcc)), "libgcc": str(libgcc), "libgcc_sha256": sha256(libgcc)}
    fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    work = CACHE / "build" / fingerprint
    work.mkdir(parents=True, exist_ok=True)
    install = work / "install"; build_dir = work / "build"; build_dir.mkdir(exist_ok=True)
    config_site = PORT / "config/xos_cache_seed.sh"
    env = os.environ.copy()
    for line in config_site.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1); env[key] = value
    env.update({
        "CONFIG_SITE": str(config_site),
        "CC": str(work / "xos-cc"), "CXX": str(work / "xos-cxx"),
        "CC_FOR_BUILD": native["clang"], "CXX_FOR_BUILD": native["clang++"],
        "CC_FOR_TARGET": gcc, "CXX_FOR_TARGET": gxx,
        "AR": obj["ar"], "AR_FOR_TARGET": obj["ar"], "AS_FOR_TARGET": obj["as"],
        "LD_FOR_TARGET": obj["ld"], "NM": obj["nm"], "RANLIB": obj["ranlib"],
        "STRIP": obj["strip"], "OBJCOPY_FOR_TARGET": obj["objcopy"],
        "OBJDUMP_FOR_TARGET": obj["objdump"], "READELF_FOR_TARGET": obj["readelf"],
        "CFLAGS": "-O2 -g0 -mno-red-zone -fno-stack-protector -fno-pic -fno-pie -mcmodel=small",
        "CXXFLAGS": "-O2 -g0 -mno-red-zone -fno-stack-protector -fno-pic -fno-pie -mcmodel=small",
        "LDFLAGS": "-static -no-pie", "MAKEINFO": "/usr/bin/true",
    })
    # A tiny allocation runtime is needed by libcpp's <new> usage; this is
    # not target libstdc++ and is kept in the private Seed build.
    cxx_runtime = None
    if stdcxx is None:
        cxx_obj = work / "cxx_runtime.o"
        run([gxx, "-std=c++20", "-O2", "-g0", "-fno-exceptions", "-fno-rtti",
             "-fno-stack-protector", "-fno-pic", "-fno-pie", "-mcmodel=small",
             "-I", str(PORT / "include"), "-I", str(sdk / "include"),
             "-c", str(PORT / "cxx_runtime.cpp"), "-o", str(cxx_obj)], env=env)
        cxx_runtime = work / "libxos_cxx_runtime.a"
        run([obj["ar"], "rcs", str(cxx_runtime), str(cxx_obj)])
    wrapper(work / "xos-cc", gcc, sdk, libgcc)
    wrapper(work / "xos-cxx", gxx, sdk, libgcc, None, stdcxx)

    log = work / "build.log"
    configure = [str(source / "configure"), *record["configure_options"]]
    if not (build_dir / "Makefile").exists():
        run(configure, cwd=build_dir, env=env, log=log)
    if configure_only:
        print(work); return work
    run([native["make"], f"-j{jobs}", "all-gcc"], cwd=build_dir, env=env, log=log)
    run([native["make"], f"-j{jobs}", "all-target-libgcc"], cwd=build_dir, env=env, log=log)
    install.mkdir(parents=True, exist_ok=True)
    run([native["make"], "install-gcc", "install-target-libgcc", f"DESTDIR={install}"], cwd=build_dir, env=env, log=log)
    tools = inspect_gcc(install, obj["readelf"])
    manifest_out = {**record, "canonical": {"build": build_triple, "host": host, "target": target},
                    "sdk_manifest": str(manifest.relative_to(ROOT)), "tools": tools,
                    "configure_log": str(log.relative_to(ROOT)), "manifest_schema": 1}
    (work / "manifest.json").write_text(json.dumps(manifest_out, indent=2, sort_keys=True) + "\n")
    print(work); return work

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sdk", type=Path, default=ROOT / "build/sdk")
    p.add_argument("--expected-sdk-manifest-sha256", required=True)
    p.add_argument("--jobs", type=int, default=6)
    p.add_argument("--configure-only", action="store_true")
    p.add_argument("--stdcxx-prefix", type=Path, default=ROOT / ".cache/xos_seed/gcc/stdcxx/prefix")
    a = p.parse_args()
    try: build(a.sdk.resolve(), a.expected_sdk_manifest_sha256, a.jobs, a.configure_only, a.stdcxx_prefix)
    except Exception as e:
        print(f"gcc build failed: {e}", file=sys.stderr); return 1
    return 0

if __name__ == "__main__": raise SystemExit(main())
