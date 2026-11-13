#!/usr/bin/env python3
"""Build and pack xxHash (xxhsum + libxxhash) for XOS from a local archive (offline)."""
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


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/xxhash: {name} is required")
    return Path(value).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None, env=None):
    print("+", " ".join(str(item) for item in command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main():
    port = json.loads((HERE / "port.json").read_text())
    lock = json.loads((HERE / "source_lock.json").read_text())
    sdk = need("XOS_SDK")
    archive = need("XOS_SOURCE_ARCHIVE")
    out = need("XOS_OUT")
    out.mkdir(parents=True, exist_ok=True)

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/xxhash: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/xxhash: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="xxhash_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"xxHash-{lock['version']}"
    if not (source / "xxhash.h").is_file():
        raise SystemExit("ports/xxhash: unexpected archive layout")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, ar, objcopy)):
        raise SystemExit("ports/xxhash: x86_64-elf-gcc/ar/objcopy must be on PATH")
    machine = subprocess.check_output([cc, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/xxhash: compiler targets {machine}, expected x86_64-elf")

    cflags = ["-O2", "-mno-red-zone", "-fno-pie", "-fno-pic",
              "-fno-stack-protector", "-idirafter", str(sdk / "include")]
    link = ["-nostdlib", "-static", "-no-pie", "-T", str(sdk / "user.ld"),
            str(sdk / "crt0_posix.o"), "-Wl,--start-group",
            str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
            str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"),
            str(sdk / "cpp/lib/libgcc.a"), "-Wl,--end-group"]

    library = work / "xxhash.o"
    run([cc, *cflags, "-c", "xxhash.c", "-o", str(library)], cwd=source)
    static_lib = work / "libxxhash.a"
    run([ar, "rcsD", str(static_lib), str(library)])

    cli = source / "cli"
    xxhsum = work / "xxhsum"
    run([cc, *cflags, f'-DXXHSUM_VERSION="{lock["version"]}"', "-I", str(cli),
         *(str(cli / name) for name in ("xxhsum.c", "xsum_os_specific.c", "xsum_arch.c",
                                        "xsum_output.c", "xsum_sanity_check.c",
                                        "xsum_bench.c")),
         *(str(source / name) for name in ("xxhash.c",)),
         str(HERE / "compat/times.c"), *link, "-o", str(xxhsum)])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    binary = tree / "usr/bin/xxhsum"
    binary.parent.mkdir(parents=True)
    run([objcopy, "--strip-all", str(xxhsum), str(binary)])
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(static_lib, libdir / "libxxhash.a")
    share = tree / "usr/share/xxhash"
    (share / "include").mkdir(parents=True)
    shutil.copyfile(source / "xxhash.h", share / "include/xxhash.h")
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/hello.txt", share / "samples/hello.txt")

    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "LICENSE", license_dir / "LICENSE.library")
    shutil.copyfile(source / "cli/COPYING", license_dir / "COPYING.cli")

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "library_license": "BSD-2-Clause (xxhash.h, libxxhash.a)",
        "cli_license": "GPL-2.0-only (xxhsum, cli/*)",
        "notes": "compat/times.c forwards newlib clock()'s times() to the SDK's _times()",
        "build": {
            "approach": "direct cross compile with the frozen XOS SDK (no upstream patch)",
            "sdk": sdk.name,
            "sdk_build_id": json.loads((sdk / "manifest.json").read_text())["build_id"],
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
            "strip": "x86_64-elf-objcopy --strip-all xxhsum",
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
        "binaries": [
            {"path": "usr/bin/xxhsum", "sha256": sha256(binary), "size": binary.stat().st_size},
        ],
        "library": {"path": "usr/lib/libxxhash.a", "sha256": sha256(libdir / "libxxhash.a"),
                    "size": (libdir / "libxxhash.a").stat().st_size},
    }
    receipt_path = share / "build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    sys.path.insert(0, str(sdk / "tools"))
    import xypm_format  # noqa: E402

    files = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        relative = path.relative_to(tree).as_posix()
        files.append({"path": relative, "type": "file", "size": path.stat().st_size,
                      "sha256": sha256(path),
                      "role": "executable" if relative == "usr/bin/xxhsum" else "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/LICENSE.library",
                     f"usr/share/licenses/{package}/COPYING.cli"],
        "build_receipt": {"path": "usr/share/xxhash/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/xxhash/source.json",
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
