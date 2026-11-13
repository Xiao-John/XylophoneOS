#!/usr/bin/env python3
"""Build and pack jq for XOS from a local archive (offline)."""
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
        raise SystemExit(f"ports/jq: {name} is required")
    return Path(value).resolve()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, cwd=None, check=True):
    print("+", " ".join(str(item) for item in command))
    return subprocess.run(command, cwd=cwd, check=check)


def main():
    port = json.loads((HERE / "port.json").read_text())
    lock = json.loads((HERE / "source_lock.json").read_text())
    sdk = need("XOS_SDK")
    archive = need("XOS_SOURCE_ARCHIVE")
    onig_lock = json.loads((HERE / "oniguruma.lock.json").read_text())
    onig_archive = need("XOS_ONIGURUMA_ARCHIVE")
    out = need("XOS_OUT")
    out.mkdir(parents=True, exist_ok=True)
    output = out / f"{port['package']['id']}-{lock['version']}.xpk"
    receipt_output = out / "build_receipt.json"
    # A reused output directory must never keep a previous success visible.
    output.unlink(missing_ok=True)
    receipt_output.unlink(missing_ok=True)
    if sha256(onig_archive) != onig_lock["sha256"]:
        raise SystemExit("ports/jq: oniguruma archive hash differs from oniguruma.lock.json")

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/jq: source archive hash differs from source_lock.json")
    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/jq: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="jq_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"jq-{lock['version']}"
    # jq needs oniguruma for its regex builtins; build a private static prefix so
    # the package stays self-contained and the recipe stays offline.
    with tarfile.open(onig_archive) as tar:
        tar.extractall(work, filter="data")
    onig_source = work / "oniguruma-6.9.10"
    if not (onig_source / "src/oniguruma.h").is_file():
        raise SystemExit("ports/jq: unexpected oniguruma archive layout")
    if not (source / "src/main.c").is_file():
        raise SystemExit("ports/jq: unexpected archive layout")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, ar, objcopy)):
        raise SystemExit("ports/jq: x86_64-elf-gcc/ar/objcopy must be on PATH")
    machine = subprocess.check_output([cc, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/jq: compiler targets {machine}, expected x86_64-elf")

    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()
    cflags = (f"-O2 -mno-red-zone -fno-pie -fno-pic -fno-stack-protector "
              f"-idirafter {sdk}/include -D_POSIX_THREADS=1 "
              "-D_POSIX_READER_WRITER_LOCKS=200809L -D_UNIX98_THREAD_MUTEX_ATTRIBUTES=1")
    prefix = work / "onig-prefix"
    (prefix / "include").mkdir(parents=True)
    (prefix / "lib").mkdir()
    toolchain = work / "onig_toolchain.cmake"
    toolchain.write_text(
        "set(CMAKE_SYSTEM_NAME Generic)\n"
        "set(CMAKE_SYSTEM_PROCESSOR x86_64)\n"
        f"set(CMAKE_C_COMPILER {cc})\n"
        "set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)\n")
    cmake = shutil.which("cmake")
    if cmake is None:
        raise SystemExit("ports/jq: cmake is required to build oniguruma")
    onig_build = work / "onig-build"
    run([cmake, "-S", str(onig_source), "-B", str(onig_build),
         f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", "-DBUILD_SHARED_LIBS=OFF",
         "-DCMAKE_BUILD_TYPE=Release", f"-DCMAKE_C_FLAGS={cflags}"])
    run([cmake, "--build", str(onig_build), "--target", "onig", "-j", "4"])
    configure = ["./configure", "--host=x86_64-elf", "--build=aarch64-apple-darwin",
                 f"--with-oniguruma={prefix}", "--disable-maintainer-mode", "--disable-docs",
                 "--disable-shared", "--enable-static", f"CC={cc}", f"CFLAGS={cflags}",
                 f"LDFLAGS=-nostdlib -static -no-pie -T {sdk}/user.ld {sdk}/crt0_posix.o",
                 "LIBS=-Wl,--start-group "
                 f"{sdk}/lib/libxos.a {sdk}/lib/libxos_loader.a {sdk}/lib/libc.a "
                 f"{sdk}/lib/libm.a {libgcc} -Wl,--end-group"]

    shutil.copyfile(onig_build / "libonig.a", prefix / "lib/libonig.a")
    for name in ("oniguruma.h", "oniggnu.h", "onigposix.h"):
        shutil.copyfile(onig_source / "src" / name, prefix / "include" / name)
    run(configure, cwd=source)
    run(["make", "src/builtin.inc", "src/version.h"], cwd=source)
    # libtool rejects the SDK crt0 object in LDFLAGS; compile objects only, then link.
    run(["make", "-k", "-j4", "libjq.la"], cwd=source, check=False)
    run(["make", "src/main.o", "src/jq_test.o"], cwd=source)
    objects = sorted((source / "src").glob("*.o"))
    if not (source / "src/jv.o").is_file() or not (source / "src/main.o").is_file():
        raise SystemExit("ports/jq: object build did not produce jv.o/main.o")

    dec_objects = []
    for name in ("decContext.c", "decNumber.c"):
        target = work / (Path(name).stem + ".o")
        run([cc, *cflags.split(), "-I", str(source / "vendor/decNumber"),
             "-c", str(source / "vendor/decNumber" / name), "-o", str(target)])
        dec_objects.append(str(target))
    binary_source = work / "jq"
    run([cc, "-nostdlib", "-static", "-no-pie", "-T", str(sdk / "user.ld"),
         str(sdk / "crt0_posix.o"), *(str(path) for path in objects),
         *dec_objects, "-L", str(prefix / "lib"), "-lonig",
         "-Wl,--start-group", str(sdk / "lib/libxos.a"),
         str(sdk / "lib/libxos_loader.a"), str(sdk / "lib/libc.a"),
         str(sdk / "lib/libm.a"), libgcc, "-Wl,--end-group", "-o", str(binary_source)])

    library_objects = [str(p) for p in objects
                       if p.name not in ("main.o", "jq_test.o")] + dec_objects
    static_lib = work / "libjq.a"
    run([ar, "rcsD", str(static_lib), *library_objects])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    binary = tree / "usr/bin/jq"
    binary.parent.mkdir(parents=True)
    run([objcopy, "--strip-all", str(binary_source), str(binary)])
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(static_lib, libdir / "libjq.a")
    share = tree / "usr/share/jq"
    include = share / "include"
    include.mkdir(parents=True)
    for name in ("jq.h", "jv.h"):
        shutil.copyfile(source / "src" / name, include / name)
    (share / "samples").mkdir()
    for sample in sorted((HERE / "samples").iterdir()):
        shutil.copyfile(sample, share / "samples" / sample.name)

    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "COPYING", license_dir / "COPYING")
    shutil.copyfile(onig_source / "COPYING", license_dir / "COPYING.oniguruma")

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "license_material": "COPYING contains jq MIT, decNumber ICU and bundled notices",
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "oniguruma": {"archive": onig_lock["archive"], "sha256": onig_lock["sha256"]},
        "build": {
            "approach": "autotools configure + manual link with the frozen XOS SDK",
            "configuration": "private static oniguruma 6.9.10; decNumber enabled; static; -D_POSIX_THREADS",
            "threading": "single-thread pthread subset from the SDK (no port shim)",
            "sdk": sdk.name,
            "sdk_build_id": (json.loads((sdk / "manifest.json").read_text()).get("build_id")
                             or json.loads((sdk / "manifest.json").read_text()).get("profile", "")),
            "sdk_tree_sha256": sdk_tree_sha256,
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
            "strip": "x86_64-elf-objcopy --strip-all jq",
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
        "binaries": [{"path": "usr/bin/jq", "sha256": sha256(binary),
                      "size": binary.stat().st_size}],
        "library": {"path": "usr/lib/libjq.a", "sha256": sha256(libdir / "libjq.a"),
                    "size": (libdir / "libjq.a").stat().st_size},
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
                      "role": "executable" if relative == "usr/bin/jq" else "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/COPYING",
                     f"usr/share/licenses/{package}/COPYING.oniguruma"],
        "build_receipt": {"path": "usr/share/jq/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/jq/source.json",
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
