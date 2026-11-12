#!/usr/bin/env python3
"""Build and pack zstd (CLI + libzstd) for XOS from a local archive (offline)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROGRAM_SOURCES = ("zstdcli.c", "fileio.c", "fileio_asyncio.c", "benchzstd.c",
                   "benchfn.c", "datagen.c", "dibio.c", "lorem.c", "timefn.c", "util.c")


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/zstd: {name} is required")
    return Path(value).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None):
    print("+", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=cwd, check=True)


def main():
    port = json.loads((HERE / "port.json").read_text())
    lock = json.loads((HERE / "source_lock.json").read_text())
    sdk = need("XOS_SDK")
    archive = need("XOS_SOURCE_ARCHIVE")
    out = need("XOS_OUT")
    out.mkdir(parents=True, exist_ok=True)
    output = out / f"{port['package']['id']}-{lock['version']}.xpk"
    receipt_output = out / "build_receipt.json"
    # A reused output directory must never keep a previous success visible.
    output.unlink(missing_ok=True)
    receipt_output.unlink(missing_ok=True)

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/zstd: source archive hash differs from source_lock.json")
    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/zstd: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="zstd_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"zstd-{lock['version']}"
    if not (source / "lib/zstd.h").is_file():
        raise SystemExit("ports/zstd: unexpected archive layout")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    ranlib = shutil.which("x86_64-elf-ranlib")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, ar, ranlib, objcopy)):
        raise SystemExit("ports/zstd: x86_64-elf-gcc/ar/ranlib/objcopy must be on PATH")
    machine = subprocess.check_output([cc, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/zstd: compiler targets {machine}, expected x86_64-elf")

    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()
    cflags = (f"-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector "
              f"-idirafter {sdk}/include -D_POSIX_THREADS=1 "
              "-D_POSIX_READER_WRITER_LOCKS=200809L -D_UNIX98_THREAD_MUTEX_ATTRIBUTES=1 "
              "-DXOS_THREADED_RUNTIME")
    run(["make", "-C", str(source / "lib"), "libzstd.a", "-j", "4",
         f"CC={cc}", f"AR={ar}", f"RANLIB={ranlib}", "ZSTD_MULTITHREAD=1",
         f"CFLAGS={cflags} -DZSTD_MULTITHREAD"])
    library = source / "lib/libzstd.a"
    if not library.is_file() or library.stat().st_size < 100000:
        raise SystemExit("ports/zstd: libzstd.a build looks incomplete")

    binary_source = work / "zstd"
    run([cc, *cflags.split(), "-I", str(source / "lib"), "-I", str(source / "programs"),
         "-DZSTD_LEGACY_SUPPORT=0", "-DZSTD_NOTRACE", "-DZSTD_MULTITHREAD",
         *(str(source / "programs" / name) for name in PROGRAM_SOURCES),
         str(library), "-nostdlib", "-static", "-no-pie",
         "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"),
         "-Wl,--start-group", str(sdk / "lib/libxos.a"),
         *([str(sdk / "lib/libxos_loader.a")]
           if (sdk / "lib/libxos_loader.a").is_file() else []),
         str(sdk / "lib/libc.a"),
         str(sdk / "lib/libm.a"), libgcc, "-Wl,--end-group", "-o", str(binary_source)])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    binary = tree / "usr/bin/zstd"
    binary.parent.mkdir(parents=True)
    run([objcopy, "--strip-all", str(binary_source), str(binary)])
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(library, libdir / "libzstd.a")
    share = tree / "usr/share/zstd"
    include = share / "include"
    include.mkdir(parents=True)
    for name in ("zstd.h", "zdict.h", "zstd_errors.h"):
        shutil.copyfile(source / "lib" / name, include / name)
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/sample.txt", share / "samples/sample.txt")

    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "LICENSE", license_dir / "LICENSE")
    shutil.copyfile(source / "COPYING", license_dir / "COPYING")

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "build": {
            "approach": "upstream lib Makefile + manual CLI link with the frozen XOS SDK",
            "configuration": "threaded (ZSTD_MULTITHREAD), legacy support off, no trace",
            "sdk": sdk.name,
            "sdk_build_id": (json.loads((sdk / "manifest.json").read_text()).get("build_id")
                             or json.loads((sdk / "manifest.json").read_text()).get("profile", "")),
            "sdk_tree_sha256": sdk_tree_sha256,
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
            "strip": "x86_64-elf-objcopy --strip-all zstd",
        },
    }
    (share / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")

    receipt = {
        "format_version": 1,
        "package_id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "status": "cross_built_guest_not_run",
        "recipe_sha256": sha256(HERE / "build.py"),
        "sdk": provenance["build"],
        "input": {"archive": lock["archive"], "sha256": lock["sha256"]},
        "binaries": [{"path": "usr/bin/zstd", "sha256": sha256(binary),
                      "size": binary.stat().st_size}],
        "library": {"path": "usr/lib/libzstd.a", "sha256": sha256(libdir / "libzstd.a"),
                    "size": (libdir / "libzstd.a").stat().st_size},
    }
    receipt_path = share / "build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    for candidate in (sdk / "tools", HERE.parents[2] / "scripts"):
        if (candidate / "xypm_format.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import xypm_format  # noqa: E402

    files = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        relative = path.relative_to(tree).as_posix()
        files.append({"path": relative, "type": "file", "size": path.stat().st_size,
                      "sha256": sha256(path),
                      "role": "executable" if relative == "usr/bin/zstd" else "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io", "threads"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/LICENSE",
                     f"usr/share/licenses/{package}/COPYING"],
        "build_receipt": {"path": "usr/share/zstd/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/zstd/source.json",
    }
    output = out / f"{package}-{lock['version']}.xpk"
    output.unlink(missing_ok=True)
    result = xypm_format.pack_package(tree, manifest, output)

    final = dict(receipt, status="packed_guest_not_run",
                 outputs={"xpk": output.name, "sha256": result["sha256"]})
    (out / "build_receipt.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(work)
    print(json.dumps({"xpk": str(output), "sha256": result["sha256"],
                      "files": result["payload_files"]}, indent=2))


if __name__ == "__main__":
    main()
