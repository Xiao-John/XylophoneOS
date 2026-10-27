# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Run XOS on the one supported virtual machine configuration."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MACHINE = "pc-i440fx-10.0"


def qemu_command(image, *, vga=False, qmp=None, debug_port=None, cpu="qemu64,+rdrand", work_disk=None, iso=False):
    qemu = shutil.which(os.environ.get("QEMU", "qemu-system-x86_64"))
    if not qemu:
        raise SystemExit("QEMU not found; install it or set QEMU=/path/to/qemu-system-x86_64")
    command = [
        qemu, "-machine", MACHINE, "-accel", "tcg", "-cpu", cpu,
        "-m", "512M", "-smp", "1", "-nic", "none", "-vga", "std",
        "-rtc", "base=utc,clock=host",
    ]
    if iso:
        command += ["-cdrom", str(image), "-boot", "order=d,strict=on", "-no-reboot"]
    else:
        command += ["-drive", f"file={image},format=raw,if=floppy,index=0,readonly=on",
                    "-boot", "order=a,strict=on", "-no-reboot"]
    command += [
        "-monitor", "none", "-serial", "stdio",
        "-display", "cocoa" if vga else "none",
    ]
    if work_disk is not None:
        command += ["-drive", f"file={work_disk},format=raw,if=ide,index=0,media=disk,cache=writeback"]
    if qmp:
        command += ["-qmp", f"unix:{qmp},server=on,wait=off"]
    if debug_port is not None:
        command += ["-S", "-gdb", f"tcp:127.0.0.1:{debug_port}"]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vga", action="store_true", help="open a macOS VGA window")
    parser.add_argument("--real-mode", action="store_true", help="run the original 16-bit exercise")
    parser.add_argument("--debug-port", type=int, help="pause at reset and listen on loopback for LLDB/GDB")
    parser.add_argument("--work-disk", type=Path, help="existing FAT16/FAT32 work disk image")
    parser.add_argument("--iso", action="store_true", help="boot the embedded-kernel build/xos.iso")
    parser.add_argument("--iso-file", action="store_true", help="boot the file-backed build/xos-install.iso")
    parser.add_argument("--install-iso", action="store_true", help="boot build/xos-install-dash.iso")
    args = parser.parse_args()
    image = ROOT / "build" / ("real_mode.img" if args.real_mode else
                              "xos-install-dash.iso" if args.install_iso else
                              "xos-install.iso" if args.iso_file else
                              "xos.iso" if args.iso else "xos.img")
    if not image.is_file():
        raise SystemExit("Run make build first")
    work_disk = args.work_disk
    if work_disk is None and not args.real_mode:
        work_disk = ROOT / "work_disk.img"
        if not work_disk.is_file():
            raise SystemExit("Work disk missing; run 'make disk' once, or pass --work-disk")
    if args.debug_port is not None:
        print(f"Guest paused at reset; debugger listening on 127.0.0.1:{args.debug_port}", flush=True)
    try:
        subprocess.run(qemu_command(image, vga=args.vga, debug_port=args.debug_port,
                                    work_disk=None if args.real_mode else work_disk,
                                    iso=args.iso or args.iso_file or args.install_iso), check=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
