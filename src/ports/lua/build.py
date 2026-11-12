#!/usr/bin/env python3
"""Build and pack Lua (interpreter + liblua) for XOS from a local archive (offline)."""
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
LIB_SOURCES = (
    "lapi.c", "lauxlib.c", "lbaselib.c", "lcode.c", "lcorolib.c", "lctype.c",
    "ldblib.c", "ldebug.c", "ldo.c", "ldump.c", "lfunc.c", "lgc.c", "linit.c",
    "liolib.c", "llex.c", "lmathlib.c", "lmem.c", "loadlib.c", "lobject.c",
    "lopcodes.c", "loslib.c", "lparser.c", "lstate.c", "lstring.c", "lstrlib.c",
    "ltable.c", "ltablib.c", "ltm.c", "lundump.c", "lutf8lib.c", "lvm.c", "lzio.c",
)


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/lua: {name} is required")
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

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/lua: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/lua: SDK is missing {name}")

    work = Path(tempfile.mkdtemp(prefix="lua_build_", dir=out))
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"lua-{lock['version']}"
    if not (source / "src/lua.c").is_file():
        raise SystemExit("ports/lua: unexpected archive layout")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, ar, objcopy)):
        raise SystemExit("ports/lua: x86_64-elf-gcc/ar/objcopy must be on PATH")
    machine = subprocess.check_output([cc, "-dumpmachine"], text=True).strip()
    if machine != "x86_64-elf":
        raise SystemExit(f"ports/lua: compiler targets {machine}, expected x86_64-elf")

    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()
    src = source / "src"
    cflags = ["-O2", "-std=c99", "-mno-red-zone", "-fno-pie", "-fno-pic",
              "-fno-stack-protector", "-idirafter", str(sdk / "include")]
    link = ["-nostdlib", "-static", "-no-pie", "-T", str(sdk / "user.ld"),
            str(sdk / "crt0_posix.o"), "-Wl,--start-group",
            str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
            str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc,
            "-Wl,--end-group"]

    objects = []
    for name in LIB_SOURCES:
        target = work / (Path(name).stem + ".o")
        run([cc, *cflags, "-c", str(src / name), "-o", str(target)])
        objects.append(str(target))
    static_lib = work / "liblua.a"
    run([ar, "rcsD", str(static_lib), *objects])

    binary_source = work / "lua"
    run([cc, *cflags, str(src / "lua.c"), *objects, *link, "-o", str(binary_source)])

    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    binary = tree / "usr/bin/lua"
    binary.parent.mkdir(parents=True)
    run([objcopy, "--strip-all", str(binary_source), str(binary)])
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(static_lib, libdir / "liblua.a")
    share = tree / "usr/share/lua"
    include = share / "include"
    include.mkdir(parents=True)
    for name in ("lua.h", "luaconf.h", "lauxlib.h", "lualib.h"):
        shutil.copyfile(src / name, include / name)
    (share / "samples").mkdir()
    shutil.copyfile(HERE / "samples/hello.lua", share / "samples/hello.lua")

    package = port["package"]["id"]
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    shutil.copyfile(source / "doc/readme.html", license_dir / "readme.html")

    provenance = {
        "package": package,
        "upstream": port["name"],
        "version": lock["version"],
        "license": port["license"],
        "license_material": "doc/readme.html contains the MIT license text",
        "archive": lock["archive"],
        "archive_sha256": lock["sha256"],
        "archive_mirror": lock["url"],
        "sha256_scope": lock.get("sha256_scope", "upstream_release"),
        "build": {
            "approach": "direct cross compile with the frozen XOS SDK (no upstream patch)",
            "configuration": "default C99 build (no LUA_USE_POSIX: no popen/readline)",
            "sdk": sdk.name,
            "sdk_build_id": json.loads((sdk / "manifest.json").read_text())["build_id"],
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
            "strip": "x86_64-elf-objcopy --strip-all lua",
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
        "binaries": [{"path": "usr/bin/lua", "sha256": sha256(binary),
                      "size": binary.stat().st_size}],
        "library": {"path": "usr/lib/liblua.a", "sha256": sha256(libdir / "liblua.a"),
                    "size": (libdir / "liblua.a").stat().st_size},
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
                      "role": "executable" if relative == "usr/bin/lua" else "data"})
    manifest = {
        "format_version": 1,
        "id": package,
        "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/readme.html"],
        "build_receipt": {"path": "usr/share/lua/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock['archive']} sha256 {lock['sha256']} ({lock['url']}); "
                  "provenance in usr/share/lua/source.json",
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
