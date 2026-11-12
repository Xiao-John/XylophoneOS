# SPDX-License-Identifier: Apache-2.0
"""Guest file identity/cwd/fork/exec and real near-full FAT16 acceptance."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo_root / "scripts"), str(repo_root / "tests")]
from boot_smoke import Guest
from dash_b2_smoke import build_probe
from make_work_disk import make_image
from process_smoke import command, resources
from task_smoke import send_bytes, pump
from work_disk import transfer


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", type=Path, default=repo_root / "build")
    parser.add_argument("--dash-elf", type=Path, help="explicit freshly built dash for the second shell entrance")
    parser.add_argument("--report", type=Path, default=repo_root / "build/file_identity_guest_report.json")
    args = parser.parse_args()
    system = args.system.resolve()
    manifest = json.loads((system / "manifest.json").read_text())
    report = {"status": "failed", "build_id": manifest["build_id"],
              "image_sha256": sha(system / "xos-install.iso"), "checks": [],
              "dash": "not_run_no_explicit_dash" if args.dash_elf is None else "pending"}
    guest = None
    try:
        if report["image_sha256"] != manifest["artifacts"]["xos-install.iso"]["sha256"]:
            raise AssertionError("system image does not match its manifest")
        for path, expected in manifest["sources"].items():
            if sha(repo_root / path) != expected:
                raise AssertionError("source changed since system build: " + path)
        with tempfile.TemporaryDirectory(prefix="xos_file_identity_guest_") as temporary:
            folder = Path(temporary)
            probe = folder / "file_identity.elf"
            build_probe(repo_root / "tests/fixtures/file_semantics/file_identity_guest.cpp", probe, system / "sdk")
            report["probe_sha256"] = sha(probe)
            base = folder / "base.img"
            base.write_bytes(make_image())
            transfer(base, "mkdir", "/bin")
            transfer(base, "import", "/bin/file_identity.elf", probe)
            transfer(base, "import", "/hello.elf", system / "user_hello.image.elf")
            if args.dash_elf is not None:
                transfer(base, "import", "/bin/dash", args.dash_elf)
                report["dash_sha256"] = sha(args.dash_elf)
                script = folder / "identity.sh"
                script.write_text("exec /bin/file_identity.elf run\n")
                transfer(base, "import", "/identity.sh", script)
            preparer = folder / "prepare_near_full"
            subprocess.run([shutil.which("c++") or "c++", "-std=c++17", "-O1", "-w",
                            "-I" + str(repo_root / "src/third_party/fatfs"),
                            "-I" + str(repo_root / "src/user/include"),
                            "-I" + str(repo_root / "src/shared/include"),
                            str(repo_root / "tests/fixtures/file_semantics/prepare_near_full.cpp"),
                            str(repo_root / "src/third_party/fatfs/ff.c"),
                            str(repo_root / "src/user/services/fatfs_unicode.cpp"), "-o", str(preparer)], check=True)
            near_full = folder / "near_full.img"
            subprocess.run([preparer, base, near_full], check=True)
            runs = [("xsh", "exec-driver /bin/file_identity.elf run", b"FILE_IDENTITY_GUEST_OK", base),
                    ("near_full", "exec-driver /bin/file_identity.elf near_full", b"FILE_IDENTITY_NEAR_FULL_OK", near_full)]
            if args.dash_elf is not None:
                runs.append(("dash", "exec-driver /bin/dash /identity.sh", b"FILE_IDENTITY_GUEST_OK", base))
            for label, line, marker, prepared in runs:
                disk = folder / ("run_" + label + ".img")
                shutil.copyfile(prepared, disk)
                guest = Guest(system / "xos-install.iso", "file_identity_" + label, work_disk=disk, iso=True)
                guest.expect(b"xos64> ", timeout=30)
                start = len(guest.output)
                send_bytes(guest, b"run\r")
                guest.expect_supervisor(trace=True, start=start, timeout=30)
                pump(guest, 1.5)
                before = resources(guest)
                output = command(guest, line, b"kind=exited code=", timeout=240)
                if marker not in output or b"kind=exited code=0" not in output or b"[file identity] FAILED" in output:
                    raise AssertionError(output[-6000:])
                command(guest, "sync", b"[files] sync=ok")
                if resources(guest) != before:
                    raise AssertionError(label + " did not reclaim process resources")
                guest.close()
                guest = None
                report["checks"].append(label + "_public_api_and_resource_reclaim")
            report["status"] = "passed"
            if args.dash_elf is not None:
                report["dash"] = "passed"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS file identity guest: " + ", ".join(report["checks"]))


if __name__ == "__main__":
    main()
