# SPDX-License-Identifier: Apache-2.0
"""Run the actual supervisor-authorized user driver with QEMU user networking.

Checks ARP TX/RX, an IRQ event, reset-observed release and repeated-launch
resource stability. Failure to start a guest is NOT_RUN, never a mock pass.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
from boot_smoke import Guest
from process_smoke import command, resources
from task_smoke import send_bytes, pump


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "build/virtio_net_user")
    args = parser.parse_args()
    system = args.system.resolve()
    manifest = json.loads((system / "manifest.json").read_text())
    for name, digest in manifest["sources"].items():
        if sha(ROOT / name) != digest:
            raise SystemExit(f"System source mismatch: {name}")
    for name, artifact in manifest["artifacts"].items():
        if sha(system / name) != artifact["sha256"]:
            raise SystemExit(f"System artifact mismatch: {name}")
    out = args.output.resolve()
    out.relative_to(ROOT / "build")
    out.mkdir(parents=True, exist_ok=True)
    image = system / "xos-install.iso"
    report = {"status": "failed", "guest_qualification": "running", "build_id": manifest["build_id"],
              "image_sha256": sha(image), "checks": [], "not_run": ["tcp", "dns", "tls", "untrusted_dma_isolation"]}
    guest = None
    try:
        guest = Guest(image, str(out.relative_to(ROOT / "build")) + "/guest", iso=True, network=True)
        report["qemu_command"] = guest.command
        guest.expect(b"xos64> ", timeout=60)
        send_bytes(guest, b"run\r")
        guest.expect_supervisor(trace=True, timeout=60)
        command(guest, "demo keep", b"demo: keep")
        for pid in (1, 3, 4):
            command(guest, f"kill {pid}", b"kill: accepted")
        pump(guest, .3)
        steady = None
        for cycle in range(3):
            output = command(guest, "net-probe 41", b"kind=exited code=0", timeout=30)
            assert b"NET_USER_DRIVER_PASS" in output and b"[net] close=0" in output, output[-2000:]
            report["checks"].append(f"user_driver_tx_rx_irq_reset_release_{cycle}")
            current = resources(guest)
            if steady is None:
                steady = current  # One bounded kernel reset-observer mapping persists per physical device.
            else:
                assert current == steady, (current, steady)
        report["stable_resources"] = steady
        report["status"] = "passed"
        report["guest_qualification"] = "passed_with_limits"
    finally:
        if report["status"] != "passed":
            report["guest_qualification"] = "failed" if guest else "not_run"
        if guest:
            (out / "serial.log").write_bytes(guest.output)
            guest.close()
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
