# SPDX-License-Identifier: Apache-2.0
"""Build Open Adventure inside XOS (yaml + gcc) and run a Chinese-output gate."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from gcc_seed_smoke import import_manifest_files, read_manifest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer

PORT = ROOT / "src/ports/adventure"
ARCHIVE = ROOT / ".cache/xos_seed/adventure/open-adventure-1.12.tar.gz"
ARCHIVE_SHA256 = "b6db9554157c87907dd2d90f0190217cc826faee5781765b6026ca5ce90235f2"
EXPECTED = {
    "dungeon.c": "9a2081708f06651a79fc67119f20d29598c79b4999017b0e3b4840a1f97e874c",
    "dungeon.h": "d3d7553b9525d117332869c9658e61e3b1e27e9d29e81ad70880f9c2bc3a3a23",
}
STDLIB = ("encodings/__init__.py", "encodings/aliases.py", "encodings/utf_8.py",
          "codecs.py", "linecache.py", "os.py", "abc.py", "_collections_abc.py",
          "stat.py", "posixpath.py", "genericpath.py", "warnings.py")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def latest(glob, report=None):
    for path in sorted(ROOT.glob(glob), key=lambda item: item.stat().st_mtime, reverse=True):
        if report is None or report(path):
            return path
    raise SystemExit(f"missing build artifact: {glob}")


def stage(folder):
    source = folder / "open-adventure"
    source.mkdir()
    with tarfile.open(ARCHIVE) as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if not parts or Path(member.name).is_absolute() or ".." in parts:
                raise SystemExit("unsafe archive member")
            member.name = str(Path(*parts[1:]))
            if member.name != ".":
                try:
                    bundle.extract(member, source, filter="data")
                except TypeError:
                    bundle.extract(member, source)
    subprocess.run(["patch", "-p1", "--forward", "-i",
                    str(PORT / "patches/0001_xos_runtime.patch")],
                   cwd=source, check=True, stdout=subprocess.DEVNULL)
    shutil.copyfile(PORT / "adventure.yaml", source / "adventure.yaml")
    shutil.copyfile(PORT / "xos/yaml.py", source / "yaml.py")
    shutil.copyfile(PORT / "xos_readline.cpp", source / "xos_readline.cpp")
    shutil.copytree(PORT / "include", source / "include")
    shutil.copyfile(PORT / "build.sh", source / "build.sh")
    return source


def build_in_guest(folder, guest, report):
    """Run build.sh inside XOS; returns True on exit code 0."""
    start = len(guest.output)
    send_bytes(guest, b"dash /src/open-adventure/build.sh\r")
    guest.expect(b"kind=exited code=", start=start, timeout=600)
    exited = guest.output.find(b"kind=exited code=", start)
    guest.expect_any((b"xsh> ", b"sup> "), start=exited, timeout=60)
    build_output = bytes(guest.output[start:])
    report["checks"].append({"name": "in-xos-build",
                             "passed": b"kind=exited code=0" in build_output,
                             "tail": build_output[-600:].decode("utf-8", "replace")})
    return b"kind=exited code=0" in build_output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/adventure_report.json")
    parser.add_argument("--export-elf", type=Path,
                        help="also export the XOS-built /out/advent ELF here")
    parser.add_argument("--export-generated", type=Path,
                        help="also export dungeon.c/h into this directory")
    args = parser.parse_args()
    assert sha256(ARCHIVE) == ARCHIVE_SHA256
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {"gate": "ADV0 in-XOS build + Chinese output",
              "build_id": system["build_id"],
              "xos_image_sha256": sha256(ROOT / "build/xos.img"),
              "checks": [], "status": "failed"}
    with tempfile.TemporaryDirectory(prefix="xos_adventure_") as folder:
        folder = Path(folder)
        source = stage(folder)
        disk = folder / "adv.img"
        create_fat32(disk, 2048)
        created = set()

        def ensure(path):
            chain = ""
            for part in path.strip("/").split("/"):
                chain += "/" + part
                if chain not in created:
                    transfer(disk, "mkdir", chain)
                    created.add(chain)

        for path in ("/src/open-adventure", "/out", "/tmp"):
            ensure(path)
        for path in sorted(source.rglob("*")):
            rel = path.relative_to(source).as_posix()
            if path.is_dir():
                ensure("/src/open-adventure/" + rel)
            elif path.suffix in (".c", ".cpp", ".h", ".py", ".sh", ".tpl",
                                 ".adoc", ".md", ".yaml", ".desktop", ".svg", ".png") \
                    or path.name in ("COPYING", "NEWS", "Makefile"):
                parent = "/src/open-adventure/" + (rel.rsplit("/", 1)[0] if "/" in rel else "")
                ensure(parent)
                transfer(disk, "import", "/src/open-adventure/" + rel, path)

        seed_path, seed = read_manifest(ROOT / "build/cpp_bundle/seed_manifest.json",
                                        ("gcc", "g++", "cc1", "cc1plus", "as", "ld"))
        import_manifest_files(disk, ROOT, seed["install_files"], "Seed")
        sysroot = json.loads((ROOT / "build/cpp_bundle/sysroot_manifest.json").read_text())
        import_manifest_files(disk, ROOT, sysroot["files"], "sysroot")
        for entry in seed["install_files"] + sysroot["files"]:
            parent = Path(entry["guest_path"]).parent.as_posix()
            while parent not in ("/", "."):
                created.add(parent)
                parent = Path(parent).parent.as_posix()

        python_work = latest(".cache/xos_seed/cpython/*/py0a_report.json",
                             lambda p: json.loads(p.read_text()).get("status") == "built_not_run").parent
        python = folder / "python3"
        shutil.copyfile(python_work / "target_build/python.exe", python)
        subprocess.run(["x86_64-elf-strip", str(python)], check=True)
        ensure("/usr/bin")
        ensure("/usr/lib/python3.14/encodings")
        transfer(disk, "import", "/usr/bin/python3", python)
        for rel in STDLIB:
            transfer(disk, "import", "/usr/lib/python3.14/" + rel,
                     python_work / "source/Lib" / rel)
        dash = latest(".cache/xos_seed/dash/*/build/src/dash")
        transfer(disk, "import", "/usr/bin/dash", dash)

        guest = Guest(ROOT / "build/xos.img", "adventure", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.5)
            send_bytes(guest, b"demo quiet\r")
            guest.expect(b"demo tasks", start=len(guest.output) - 64, timeout=20)
            pump(guest, 0.4)
            send_bytes(guest, b"trace on\r")
            guest.expect(b"xsh: trace on", start=len(guest.output) - 64, timeout=20)
            pump(guest, 0.3)

            build_in_guest(folder, guest, report)

            start = len(guest.output)
            send_bytes(guest, b"/out/advent\r")
            guest.expect(b"\xe6\xac\xa2\xe8\xbf\x8e\xe6\x9d\xa5\xe5\x88\xb0", start=start, timeout=60)
            for command in (b"no\r", b"look\r", b"quit\r", b"yes\r"):
                send_bytes(guest, command)
                pump(guest, 1.5)
            game_output = bytes(guest.output[start:])
            guest.expect_any((b"xsh> ", b"sup> "), start=start, timeout=120)
            text = game_output.decode("utf-8", "replace")
            required = ("欢迎来到冒险", "你站在一条小路的尽头", "你得了32分",
                        "你显然还是个新手", "再得14分")
            report["checks"].append({"name": "chinese-output",
                                     "passed": all(item in text for item in required),
                                     "missing": [item for item in required if item not in text],
                                     "tail": text[-700:]})
        finally:
            guest.close()

        if args.export_elf is not None:
            args.export_elf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(disk.resolve(), disk.resolve())
            transfer(disk, "export", "/out/advent", args.export_elf)
        if args.export_generated is not None:
            args.export_generated.mkdir(parents=True, exist_ok=True)
            for name in EXPECTED:
                transfer(disk, "export", "/src/open-adventure/" + name,
                         args.export_generated / name)
        for name, expected in EXPECTED.items():
            dest = folder / name
            transfer(disk, "export", "/src/open-adventure/" + name, dest)
            actual = sha256(dest)
            report["checks"].append({"name": "generated-" + name,
                                     "passed": actual == expected,
                                     "sha256": actual, "expected": expected})
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
