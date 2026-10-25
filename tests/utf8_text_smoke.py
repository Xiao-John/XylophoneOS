# SPDX-License-Identifier: Apache-2.0
"""U1: Xsh UTF-8 line editing, rejection and argv pass-through."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes
from work_disk import transfer

ARGV_SOURCE = ROOT / "tests/fixtures/utf8/argv_utf8.cpp"
PROMPTS = (b"xsh> ", b"sup> ")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compile_argv(output):
    sdk = ROOT / "build/sdk"
    cc = shutil.which("x86_64-elf-g++")
    if cc is None:
        raise SystemExit("x86_64-elf-g++ is required")
    libgcc = subprocess.check_output([cc, "-print-libgcc-file-name"], text=True).strip()
    command = [
        cc, "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic", "-fno-stack-protector",
        "-ffunction-sections", "-fdata-sections", "-isystem", str(sdk / "include"),
        "-nostdlib", "-static", "-no-pie",
        "-Wl,--gc-sections,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
        "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"),
        str(ARGV_SOURCE), "-o", str(output),
        "-Wl,--start-group", str(sdk / "lib/libxos.a"), str(sdk / "lib/libxos_loader.a"),
        str(sdk / "lib/libc.a"), str(sdk / "lib/libm.a"), libgcc, "-Wl,--end-group",
    ]
    subprocess.run(command, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=ROOT / "build/xos.img")
    parser.add_argument("--report", type=Path,
                        default=ROOT / "build/utf8_text_report.json")
    args = parser.parse_args()
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "U0/U1 UTF-8 text channel",
        "build_id": system["build_id"],
        "xos_image_sha256": sha256(args.image),
        "checks": [],
        "status": "failed",
    }
    with tempfile.TemporaryDirectory(prefix="xos_utf8_text_") as folder:
        tmp = Path(folder)
        probe = tmp / "argv_utf8.elf"
        compile_argv(probe)
        report["argv_probe_sha256"] = sha256(probe)
        disk = tmp / "utf8.img"
        create_fat32(disk, 2048)
        transfer(disk, "mkdir", "/tmp")
        transfer(disk, "import", "/tmp/argv_utf8.elf", probe)

        guest = Guest(args.image, "utf8_text", work_disk=disk)
        try:
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(start=start, timeout=40)
            pump(guest, 0.5)
            send_bytes(guest, b"demo quiet\r")
            guest.expect(b"demo tasks", start=len(guest.output) - 64, timeout=20)
            pump(guest, 0.5)

            def send(line, expected, timeout=30):
                begin = len(guest.output)
                send_bytes(guest, line)
                guest.expect(expected, start=begin, timeout=timeout)
                guest.expect_any(PROMPTS, start=begin, timeout=timeout)
                pump(guest, 0.2)
                return bytes(guest.output[begin:])

            def check(name, passed, **extra):
                report["checks"].append({"name": name, "passed": passed, **extra})

            text = send("你好\r".encode(), b"cannot read program")
            check("utf8-echo-and-argv", "你好".encode() in text and b"\xe4\xbd\xa0" in text)

            backspace = b"ab" + "é".encode() + b"\x7f" + b"c\r"
            text = send(backspace, b"not found")
            check("utf8-backspace", b"xsh: abc: not found" in text and
                  b"xsh: ab\xc3\xa9c: not found" not in text and b"\b \b" in text)

            wide = b"ab" + "你".encode() + b"\x7f" + b"cd\r"
            text = send(wide, b"not found")
            check("wide-backspace", b"xsh: abcd: not found" in text and
                  b"\b \b\b \b" in text)

            text = send(b"\xff\r", b"xsh: invalid UTF-8 input")
            check("invalid-sequence", b"xsh: invalid UTF-8 input" in text)

            text = send("/tmp/argv_utf8.elf 中文测试\r".encode(), "arg1=中文测试".encode(), timeout=60)
            check("utf8-argv", "arg1=中文测试".encode() in text)

            text = send(b"a" * 2100 + b"\r", b"xsh: input line too long", timeout=60)
            check("line-limit", b"xsh: input line too long" in text)
        finally:
            guest.close()
    report["status"] = "passed" if all(c["passed"] for c in report["checks"]) else "failed"
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
