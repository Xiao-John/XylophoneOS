# SPDX-License-Identifier: Apache-2.0
"""DU4: stage idna (type4) from an XOSBND1 ISO, then P2-install it with a guest xypm."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from task_smoke import pump, send_bytes

PREFERRED_SHA_MARKER = "ddd13972"
# Usage line only present in transactional xypm builds (install/upgrade/remove).
INSTALL_CAPABLE_MARKER = b"recover (maintenance only)"
PROFILE = ROOT / "config/package/xos_x86_64_static_single_b2_v1.json"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_current_xypm():
    """Build xypm from current source (no seed supports install on this host)."""
    sdk = ROOT / ".cache/xos_seed/xypm_sdk/single_b2_v1"
    if not sdk.is_dir():
        raise SystemExit(f"missing frozen xypm sdk: {sdk}")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_xypm.py"),
         "--sdk", str(sdk), "--profile", str(PROFILE)],
        check=True, cwd=ROOT, capture_output=True, text=True)
    match = re.search(r'"cache_key"\s*:\s*"([0-9a-f]+)"', result.stdout)
    if not match:
        raise SystemExit("build_xypm.py reported no cache_key:\n" + result.stdout[-2000:])
    manifest = ROOT / ".cache/xos_seed/xypm" / match.group(1) / "manifest.json"
    data = json.loads(manifest.read_text())
    elf = Path(data["elf"])
    if not elf.is_file() or INSTALL_CAPABLE_MARKER not in elf.read_bytes():
        raise SystemExit(f"built xypm cannot install packages: {elf}")
    return elf


def select_xypm():
    """Prefer the ddd13972 seed, but only if it can actually install."""
    candidates = []
    for elf in sorted((ROOT / ".cache/xos_seed/xypm").glob("*/project/build/xypm.elf")):
        digest = sha256(elf)
        capable = INSTALL_CAPABLE_MARKER in elf.read_bytes()
        candidates.append((elf, digest, capable))
    preferred = [row for row in candidates if PREFERRED_SHA_MARKER in row[1]]
    if preferred and preferred[0][2]:
        return preferred[0][0], preferred[0][1], "preferred-seed", ""
    capable = [row for row in candidates if row[2]]
    if capable:
        return capable[0][0], capable[0][1], "capable-seed", ""
    note = ("no seed xypm supports install"
            + (f"; preferred {PREFERRED_SHA_MARKER} seed is read-only"
               if preferred else "")
            + "; built current source via scripts/build_xypm.py")
    if preferred:
        note += f" (preferred sha {preferred[0][1]})"
    elf = build_current_xypm()
    return elf, sha256(elf), "built-current", note


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "build/iso_bundle_p2_install_report.json")
    parser.add_argument("--idna", type=Path, default=ROOT / "build/idna-3.20.xpk")
    args = parser.parse_args()
    if not args.idna.is_file():
        raise SystemExit(f"missing idna xpk: {args.idna}")

    iso = ROOT / "build/iso_bundle_p2.iso"
    manifest = ROOT / "build/iso_bundle_p2_manifest.json"
    system = json.loads((ROOT / "build/manifest.json").read_text())
    report = {
        "gate": "DU4 XOSBND1 bundle idna P2 install",
        "build_id": system["build_id"],
        "member_specs": [f"4:idna.xpk={args.idna}"],
        "checks": [],
        "status": "failed",
    }
    guest = None
    try:
        xypm_elf, xypm_sha, source_kind, note = select_xypm()
        report["xypm_seed"] = {
            "path": str(xypm_elf),
            "sha256": xypm_sha,
            "source": source_kind,
            "preferred_match": source_kind == "preferred-seed",
            "note": note,
        }

        subprocess.run([
            sys.executable, str(ROOT / "scripts/build_install_iso.py"),
            "--output", str(iso),
            "--manifest", str(manifest),
            "--member", f"4:idna.xpk={args.idna}",
        ], check=True, cwd=ROOT)
        bundle_meta = json.loads(manifest.read_text())
        bundle = bundle_meta.get("boot_bundle")
        if bundle is None:
            raise SystemExit("install manifest has no boot_bundle metadata")
        report["bundle"] = bundle
        report["iso_sha256"] = sha256(iso)
        members = bundle.get("members", [])
        kinds = {(m.get("type"), m.get("name")) for m in members}
        if (1, "dash") not in kinds or (4, "idna.xpk") not in kinds:
            raise SystemExit(f"expected dash+idna.xpk in bundle metadata, got {members}")
        if not 0 < bundle.get("container_bytes", 0) <= 33554432:
            raise SystemExit(f"container total out of budget: {bundle.get('container_bytes')}")
        report["checks"].append({"name": "bundle-metadata", "passed": True, "members": members})

        with tempfile.TemporaryDirectory(prefix="xos_bundle_p2_") as folder:
            disk = Path(folder) / "work.img"
            create_fat32(disk, 512)
            work_disk = str(ROOT / "scripts/work_disk.py")
            for operation, path in (("mkdir", "/usr"), ("mkdir", "/usr/bin")):
                subprocess.run([sys.executable, work_disk, str(disk), operation, path],
                               check=True, cwd=ROOT)
            subprocess.run([sys.executable, work_disk, str(disk), "import",
                            "/usr/bin/xypm", str(xypm_elf)], check=True, cwd=ROOT)
            report["checks"].append({"name": "xypm-imported-offline", "passed": True})

            guest = Guest(iso, "iso_bundle_p2_install", iso=True, work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            start = len(guest.output)
            send_bytes(guest, b"run\r")
            # Files-service init stages the bundle before the shell prompt appears.
            guest.expect(b"[files] bundle installed: /usr/bin/dash", start=start, timeout=180)
            guest.expect(
                b"[files] bundle installed: /var/cache/xypm/incoming/idna.xpk",
                start=start, timeout=300)
            guest.expect(b"[files] XOSBND1 bundle processed members=", start=start, timeout=120)
            guest.expect(b"members=2", start=start, timeout=10)
            report["checks"].append({"name": "idna-staged-from-bundle", "passed": True})
            guest.expect_supervisor(trace=True, start=start, timeout=300)
            pump(guest, 0.5)

            def command(line, expected, timeout=300):
                begin = len(guest.output)
                send_bytes(guest, line.encode() + b"\r")
                alternatives = expected if isinstance(expected, tuple) else (expected,)
                guest.expect_any(alternatives, start=begin, timeout=timeout)
                guest.expect_supervisor(start=begin, timeout=timeout)
                return bytes(guest.output[begin:])

            # process_guard begin needs only supervisor+files alive; stop the
            # boot demos explicitly instead of relying on any auto-install path.
            data = command(
                "demo quiet",
                (b"[sup] demo tasks stopped", b"[sup] demo tasks already stopped"), timeout=60)
            report["checks"].append({"name": "boot-demos-quiet", "passed": True,
                                     "output_tail": data[-400:].decode(errors="replace")})

            # A failed boot-time auto-install can leave the admission guard
            # retained (worker_pid stuck), which blocks every later spawn.
            # Normalize with maint-status/maint-recover; do not rely on the
            # auto-install path itself.
            status = command("maint-status", b"maintenance: owner=", timeout=60)
            report["maint_status_after_boot"] = status[-300:].decode(errors="replace")
            if b"owner=0 worker=0" not in status:
                data = command("maint-recover /usr/bin/xypm recover",
                               b"maintenance: completed", timeout=300)
                report["checks"].append({"name": "retained-guard-recovered", "passed": True,
                                         "output_tail": data[-800:].decode(errors="replace")})
            else:
                report["checks"].append({"name": "retained-guard-recovered", "passed": True,
                                         "note": "guard already clear after boot"})

            # If a concurrent auto-install already installed idna, remove
            # it first so this test still exercises its own maint-run install.
            listing = command("xypm list",
                              (b"python_idna", b"No packages installed."), timeout=60)
            if b"python_idna" in listing:
                report["auto_install_preinstalled"] = True
                command("maint-run /usr/bin/xypm remove python_idna",
                        b"maintenance: completed", timeout=300)
                report["checks"].append({"name": "preinstalled-idna-removed", "passed": True})
            else:
                report["auto_install_preinstalled"] = False

            data = command(
                "maint-run /usr/bin/xypm install /var/cache/xypm/incoming/idna.xpk",
                b"maintenance: completed", timeout=300)
            report["install_output_tail"] = data[-1500:].decode(errors="replace")
            report["checks"].append({"name": "guest-p2-install-completed", "passed": True})

            data = command("xypm list", b"python_idna", timeout=60)
            report["checks"].append({"name": "xypm-list-sees-package", "passed": True,
                                     "output_tail": data[-600:].decode(errors="replace")})

            data = command("xypm info python_idna", b"id: python_idna", timeout=60)
            report["checks"].append({"name": "xypm-info-python-idna", "passed": True,
                                     "output_tail": data[-600:].decode(errors="replace")})
            report["status"] = "passed"
    except Exception as exc:
        report["error"] = str(exc)
        if guest is not None:
            report["output_tail"] = bytes(guest.output[-8000:]).decode(errors="replace")
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": report["checks"]}, indent=2))


if __name__ == "__main__":
    main()
