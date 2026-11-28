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


def qemu_command(image, *, vga=False, display=None, qmp=None, qmp_transport="unix", debug_port=None,
                 cpu="qemu64,+rdrand", work_disk=None, iso=False, network=False, network_capture=None,
                 network_peer_port=None, network_device_id=None, qtest_pipe=None):
    if network_capture is not None and not network:
        raise ValueError("network_capture requires the explicit network profile")
    if network_peer_port is not None and (not network or isinstance(network_peer_port, bool) or
                                         not isinstance(network_peer_port, int) or not 0 < network_peer_port < 65536):
        raise ValueError("network_peer_port requires the network profile and a valid loopback TCP port")
    if network_device_id is not None and (not network or not isinstance(network_device_id, str) or
            not network_device_id or len(network_device_id) > 32 or
            any(character not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for character in network_device_id)):
        raise ValueError("network_device_id requires the network profile and a bounded QEMU identifier")
    configured_qemu = os.environ.get("QEMU", "qemu-system-x86_64")
    qemu = shutil.which(configured_qemu)
    if not qemu and "QEMU" not in os.environ and os.name == "nt":
        installed = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "qemu" / "qemu-system-x86_64.exe"
        if installed.is_file():
            qemu = str(installed)
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
        "-display", display or ("sdl" if vga else "none"),
    ]
    if work_disk is not None:
        command += ["-drive", f"file={work_disk},format=raw,if=ide,index=0,media=disk,cache=writeback"]
    if network:
        backend = ("user,id=xosnet" if network_peer_port is None else
                   f"socket,id=xosnet,connect=127.0.0.1:{network_peer_port}")
        device = "virtio-net-pci,disable-legacy=on,romfile=,netdev=xosnet,addr=05.0,mac=52:54:00:12:34:56"
        if network_device_id is not None:
            device += ',id=' + network_device_id
        command += ["-netdev", backend, "-device", device]
        if network_capture is not None:
            capture_path = str(network_capture).replace(",", ",,")
            command += ["-object", f"filter-dump,id=xos_capture,netdev=xosnet,file={capture_path}"]
    if qmp:
        if qmp_transport == "unix":
            command += ["-qmp", f"unix:{qmp},server=on,wait=off"]
        elif qmp_transport == "pipe":
            command += ["-qmp", f"pipe:{qmp}"]
        else:
            raise ValueError("QMP transport must be unix or pipe")
    if qtest_pipe is not None:
        # Explicit host hardware fixture only; normal runs expose no qtest.
        command += ["-qtest", f"pipe:{qtest_pipe}"]
    if debug_port is not None:
        command += ["-S", "-gdb", f"tcp:127.0.0.1:{debug_port}"]
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vga", action="store_true", help="open an SDL VGA window")
    parser.add_argument("--display", help="QEMU display backend (for example sdl, gtk, or none)")
    parser.add_argument("--network", action="store_true", help="enable the explicit modern VirtIO-net user-driver profile (instance 41)")
    parser.add_argument("--real-mode", action="store_true", help="run the original 16-bit exercise")
    parser.add_argument("--debug-port", type=int, help="pause at reset and listen on loopback for LLDB/GDB")
    parser.add_argument("--work-disk", type=Path, help="existing FAT16/FAT32 work disk image")
    parser.add_argument("--image", type=Path,
                        help="explicit boot image; .iso files boot with -cdrom, others as floppy")
    parser.add_argument("--iso-file", action="store_true", help="boot the file-backed build/xos-install.iso")
    parser.add_argument("--install-iso", action="store_true", help="boot build/xos-install-dash.iso")
    args = parser.parse_args()
    image = args.image.resolve() if args.image else ROOT / "build" / (
        "real_mode.img" if args.real_mode else
        "xos-install-dash.iso" if args.install_iso else
        "xos-install.iso")
    if not image.is_file():
        raise SystemExit("Run make build first")
    # .iso images boot via -cdrom; raw images (real_mode.img) keep the floppy path.
    iso_boot = image.suffix.lower() == ".iso"
    work_disk = args.work_disk
    if work_disk is None and not args.real_mode:
        work_disk = ROOT / "work_disk.img"
        if not work_disk.is_file():
            raise SystemExit("Work disk missing; run 'make disk' once, or pass --work-disk")
    if args.debug_port is not None:
        print(f"Guest paused at reset; debugger listening on 127.0.0.1:{args.debug_port}", flush=True)
    try:
        subprocess.run(qemu_command(image, vga=args.vga, display=args.display,
                                    debug_port=args.debug_port,
                                    work_disk=None if args.real_mode else work_disk,
                                    network=args.network,
                                    iso=iso_boot), check=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
