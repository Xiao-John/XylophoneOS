#!/usr/bin/env python3
"""Build and pack Oniguruma for XOS from a local archive (offline)."""
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
        raise SystemExit(f"ports/oniguruma: {name} is required")
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
        raise SystemExit("ports/oniguruma: source archive hash differs from source_lock.json")
    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/oniguruma: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="onig_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"oniguruma-{lock['version']}"
    if not (source / "src/oniguruma.h").is_file():
        raise SystemExit("ports/oniguruma: unexpected archive layout")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    if not all((cc, ar)):
        raise SystemExit("ports/oniguruma: x86_64-elf-gcc/ar must be on PATH")
    machine = subprocess.check_output([cc, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/oniguruma: compiler targets {machine}, expected x86_64-elf")
    cmake = shutil.which("cmake")
    if cmake is None:
        raise SystemExit("ports/oniguruma: cmake is required by the recipe")

    toolchain = work / "xos_toolchain.cmake"
    toolchain.write_text(
        "set(CMAKE_SYSTEM_NAME Generic)\n"
        "set(CMAKE_SYSTEM_PROCESSOR x86_64)\n"
        f"set(CMAKE_C_COMPILER {cc})\n"
        "set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)\n")
    build = work / "build"
    run([cmake, "-S", str(source), "-B", str(build),
         f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", "-DBUILD_SHARED_LIBS=OFF",
         "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_C_FLAGS="
         f"-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector "
         f"-idirafter {sdk}/include"])
    run([cmake, "--build", str(build), "--target", "onig", "-j", "4"])
    library = build / "libonig.a"
    if not library.is_file():
        raise SystemExit("ports/oniguruma: cmake did not produce libonig.a")

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(library, libdir / "libonig.a")
    share = tree / "usr/share/oniguruma"
    include = share / "include"
    include.mkdir(parents=True)
    for name in ("oniguruma.h", "oniggnu.h", "onigposix.h"):
        shutil.copyfile(source / "src" / name, include / name)
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/regex.c", share / "samples/regex.c")

    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
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
            "approach": "upstream CMake cross build with the frozen XOS SDK",
            "configuration": "static library, UTF-8/posix headers, samples/regex.c",
            "sdk": sdk.name,
            "sdk_build_id": (json.loads((sdk / "manifest.json").read_text()).get("build_id")
                             or json.loads((sdk / "manifest.json").read_text()).get("profile", "")),
            "sdk_tree_sha256": sdk_tree_sha256,
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
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
        "library": {"path": "usr/lib/libonig.a", "sha256": sha256(libdir / "libonig.a"),
                    "size": (libdir / "libonig.a").stat().st_size},
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
                      "sha256": sha256(path), "role": "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/COPYING"],
        "build_receipt": {"path": "usr/share/oniguruma/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/oniguruma/source.json",
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
