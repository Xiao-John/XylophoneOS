#!/usr/bin/env python3
"""Build ncursesw 6.5 (bounded profile) for XOS from a local archive (offline)."""
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

PUBLIC_HEADERS = ('curses.h', 'term.h', 'termcap.h', 'unctrl.h', 'ncurses_dll.h',
                  'ncursesw/curses.h', 'ncursesw/term.h', 'ncursesw/termcap.h',
                  'ncursesw/unctrl.h', 'ncursesw/ncurses_dll.h')


def need(name):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"ports/ncursesw: {name} is required")
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
    output = out / f"{port['package']['id']}-{lock['version']}.xpk"
    receipt_output = out / "build_receipt.json"
    output.unlink(missing_ok=True)
    receipt_output.unlink(missing_ok=True)

    if sha256(archive) != lock["sha256"]:
        raise SystemExit("ports/ncursesw: source archive hash differs from source_lock.json")
    for name in ("manifest.json", "user.ld", "crt0_posix.o"):
        if not (sdk / name).is_file():
            raise SystemExit(f"ports/ncursesw: SDK is missing {name}")

    sys.path.insert(0, str(HERE.parents[2] / "scripts"))
    from xos_app import tree_receipt
    sdk_tree_sha256 = tree_receipt(sdk)[0]
    profile_name = port["package"]["target_profile"].replace("-", "_") + ".json"
    profile_path = HERE.parents[2] / "config/package" / profile_name
    if profile_path.is_file():
        registered = json.loads(profile_path.read_text()).get("sdk_tree_sha256", [])
        if sdk_tree_sha256 not in registered and os.environ.get("XOS_SDK_UNREGISTERED_OK") != "1":
            raise SystemExit("ports/ncursesw: SDK tree is not registered for the target profile")

    cc = shutil.which("x86_64-elf-gcc")
    ar = shutil.which("x86_64-elf-ar")
    ranlib = shutil.which("x86_64-elf-ranlib")
    objcopy = shutil.which("x86_64-elf-objcopy")
    if not all((cc, ar, ranlib, objcopy)):
        raise SystemExit("ports/ncursesw: x86_64-elf-gcc/ar/ranlib/objcopy must be on PATH")
    cc_build = shutil.which("cc") or shutil.which("gcc") or cc
    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()

    work = Path(tempfile.mkdtemp(prefix="ncursesw_build_", dir=out))
    try:
        _build(port, lock, sdk, archive, out, output, receipt_output, work,
               cc, cc_build, ar, ranlib, objcopy, libgcc, sdk_tree_sha256)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _build(port, lock, sdk, archive, out, output, receipt_output, work,
           cc, cc_build, ar, ranlib, objcopy, libgcc, sdk_tree_sha256):
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    source = work / f"ncurses-{lock['version']}"
    if not (source / "configure").is_file():
        raise SystemExit("ports/ncursesw: unexpected archive layout")

    cflags = ["-O2", "-mno-red-zone", "-fno-pie", "-fno-pic",
              "-fno-stack-protector", "-idirafter", f"{sdk}/include",
              "-D_XOPEN_SOURCE=700", "-D_XOPEN_SOURCE_EXTENDED=1"]
    env = dict(os.environ)
    env.update({
        "CC": cc, "BUILD_CC": cc_build, "AR": ar, "RANLIB": ranlib,
        "CFLAGS": shlex.join(cflags),
        "CPPFLAGS": shlex.join(["-idirafter", f"{sdk}/include"]),
        "LDFLAGS": shlex.join(["-nostdlib", "-static", "-no-pie",
                               "-T", f"{sdk}/user.ld", f"{sdk}/crt0_posix.o"]),
        "LIBS": shlex.join(["-Wl,--start-group",
                            f"{sdk}/lib/libxos.a", f"{sdk}/lib/libxos_loader.a",
                            f"{sdk}/lib/libc.a", f"{sdk}/lib/libm.a",
                            "-Wl,--end-group"]),
    })

    configure_cmd = [
        str(source / "configure"),
        f"--build={subprocess.check_output(['uname', '-m'], text=True).strip()}-apple-darwin",
        "--host=x86_64-unknown-elf",
        "--enable-widec", "--without-shared", "--without-cxx",
        "--without-cxx-binding", "--without-ada", "--without-progs",
        "--without-tests", "--without-debug", "--disable-sigwinch",
    ]
    run(configure_cmd, cwd=source, env=env)

    # ncurses generated term.h includes sgtty.h which newlib lacks; provide a stub.
    sgtty_stub = sdk / "include/sgtty.h"
    if not sgtty_stub.is_file():
        sgtty_stub.write_text(
            "/* Stub for ncurses term.h compatibility. */\n"
            "#ifndef _SGTTY_H\n#define _SGTTY_H\n"
            "struct sgttyb { char sg_ispeed, sg_ospeed, sg_erase, sg_kill; short sg_flags; };\n"
            "#endif\n")

    run(["make", "-j4"], cwd=source, env=env)

    library = source / "lib/libncursesw.a"
    if not library.is_file():
        raise SystemExit("ports/ncursesw: libncursesw.a was not produced")

    # Generate terminfo with host tic
    tic_source = source / "progs/tic.c"
    terminfo_db = work / "terminfo"
    terminfo_db.mkdir(parents=True, exist_ok=True)
    # Use host tic if available, otherwise build one from source
    tic = shutil.which("tic")
    if tic is None:
        # Build host tic from ncurses source
        run([cc_build, "-O2", "-I", str(source / "include"),
             str(source / "progs/tic.c"), str(source / "progs/tparm_type.c"),
             str(source / "progs/infocmp.c"),
             f"-L{source}/lib", "-lncursesw", "-o", str(work / "tic")],
            cwd=source, env=env)
        tic = str(work / "tic")
    terminfo_ok = False
    try:
        run([tic, "-x", "-e", "xterm", "-o", str(terminfo_db),
             str(source / "misc/terminfo.src")])
        terminfo_ok = (terminfo_db / "x/xterm").is_file()
    except subprocess.CalledProcessError:
        print("WARNING: terminfo generation failed; terminfo will be empty")
    if not terminfo_ok:
        terminfo_db.mkdir(parents=True, exist_ok=True)

    # Build consumer probes
    consumers = {}
    consumer_dir = HERE.parents[2] / "tests/fixtures/ncursesw"
    for name in ("wide_screen_probe", "reentry_probe"):
        source_file = consumer_dir / f"{name}.c"
        if not source_file.is_file():
            raise SystemExit(f"ports/ncursesw: missing consumer probe {source_file}")
        binary = work / name
        run([cc, *cflags, "-I", str(source / "include"),
             "-D_XOPEN_SOURCE_EXTENDED=1",
             str(source_file),
             str(library),
             "-nostdlib", "-static", "-no-pie",
             "-T", f"{sdk}/user.ld", f"{sdk}/crt0_posix.o",
             "-Wl,--start-group",
             f"{sdk}/lib/libxos.a", f"{sdk}/lib/libxos_loader.a",
             f"{sdk}/lib/libc.a", f"{sdk}/lib/libm.a", libgcc,
             "-Wl,--end-group",
             "-o", str(binary)])
        consumers[name] = binary

    # Package
    tree = out / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    package = port["package"]["id"]

    # Library
    libdir = tree / "usr/lib"
    libdir.mkdir(parents=True)
    shutil.copyfile(library, libdir / "libncursesw.a")

    # Headers
    include_dir = tree / "usr/share/ncursesw/include"
    include_dir.mkdir(parents=True)
    for header in PUBLIC_HEADERS:
        src = source / "include" / header
        if src.is_file():
            dest = include_dir / Path(header).name
            shutil.copyfile(src, dest)

    # Terminfo
    terminfo_dir = tree / "usr/share/terminfo"
    terminfo_dir.mkdir(parents=True)
    shutil.copytree(terminfo_db, terminfo_dir, dirs_exist_ok=True)

    # Consumer probes
    bin_dir = tree / "usr/bin"
    bin_dir.mkdir(parents=True)
    for name, binary in consumers.items():
        run([objcopy, "--strip-all", str(binary), str(bin_dir / name)])

    # License
    license_dir = tree / f"usr/share/licenses/{package}"
    license_dir.mkdir(parents=True)
    notice_hash = lock.get("notice_sha256", "")
    if notice_hash and sha256(HERE / "upstream/COPYING") != notice_hash:
        raise SystemExit("ports/ncursesw: upstream COPYING hash differs from lock")
    shutil.copyfile(HERE / "upstream/COPYING", license_dir / "COPYING")
    if (HERE / "upstream/terminfo-source-notice.txt").is_file():
        shutil.copyfile(HERE / "upstream/terminfo-source-notice.txt",
                        license_dir / "terminfo-source-notice.txt")

    # Provenance
    share = tree / "usr/share/ncursesw"
    share.mkdir(parents=True, exist_ok=True)
    provenance = {
        "package": package, "upstream": port["name"], "version": lock["version"],
        "license": port["license"],
        "archive": lock.get("url", ""), "archive_sha256": lock["sha256"],
        "notes": f"bounded profile: widec, single-thread, 24x80 serial, "
                 f"terminfo={'generated' if terminfo_ok else 'empty'}",
        "build": {
            "approach": "configure --enable-widec --without-shared --disable-sigwinch",
            "sdk": sdk.name,
            "sdk_tree_sha256": sdk_tree_sha256,
            "compiler": subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
        },
    }
    (share / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")
    receipt = {
        "format_version": 1, "package_id": package, "upstream_version": lock["version"],
        "revision": 0, "status": "cross_built_guest_not_run",
        "recipe_sha256": sha256(HERE / "build.py"),
        "sdk": provenance["build"],
        "input": {"archive_sha256": lock["sha256"]},
        "binaries": [{"path": f"usr/bin/{name}", "sha256": sha256(bin_dir / name),
                      "size": (bin_dir / name).stat().st_size}
                     for name in consumers],
    }
    receipt_path = share / "build_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    # Pack
    for candidate in (sdk / "tools", HERE.parents[2] / "scripts"):
        if (candidate / "xypm_format.py").is_file():
            sys.path.insert(0, str(candidate))
            break
    import xypm_format  # noqa: E402

    files = []
    for path in sorted(p for p in tree.rglob("*") if p.is_file()):
        relative = path.relative_to(tree).as_posix()
        if not relative.startswith(("usr/bin/", "usr/lib/", "usr/share/")):
            continue
        files.append({"path": relative, "type": "file", "size": path.stat().st_size,
                      "sha256": sha256(path),
                      "role": "executable" if relative.startswith("usr/bin/") else "data"})
    manifest = {
        "format_version": 1, "id": package, "upstream_version": lock["version"],
        "revision": 0,
        "target_profile": port["package"]["target_profile"],
        "required_features": ["stdio", "heap", "file_io"],
        "runtime_dependencies": [],
        "files": files,
        "licenses": [f"usr/share/licenses/{package}/COPYING"],
        "build_receipt": {"path": "usr/share/ncursesw/build_receipt.json",
                          "sha256": sha256(receipt_path)},
        "source": f"{lock.get('url','')} sha256 {lock['sha256']}",
    }
    result = xypm_format.pack_package(tree, manifest, output)
    final = dict(receipt, status="packed_guest_not_run",
                 terminfo={"generated": terminfo_ok},
                 outputs={"xpk": output.name, "sha256": result["sha256"]})
    receipt_output.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(work)
    print(json.dumps({"xpk": str(output), "sha256": result["sha256"],
                      "files": result["payload_files"]}, indent=2))


if __name__ == "__main__":
    main()
