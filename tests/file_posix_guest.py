# SPDX-License-Identifier: Apache-2.0
"""Guest-level POSIX path, offset, rename and spawn-action acceptance."""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from make_work_disk import create_fat32
from work_disk import transfer
from e08_storage_smoke import boot
from process_smoke import command, resources
from dash_b2_smoke import build_probe


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    system = json.loads((ROOT / "build/manifest.json").read_text())
    sdk = ROOT / "build/sdk"
    report = {"status": "failed", "build_id": system["build_id"],
              "image_sha256": sha(ROOT / "build/xos.img"), "checks": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_file_posix_") as folder:
            folder = Path(folder)
            probe = ROOT / "build/file_posix_guest.elf"
            build_probe(ROOT / "tests/fixtures/file_posix/file_posix.c", probe, sdk)
            report["probe_sha256"] = sha(probe)
            disk = folder / "work.img"
            create_fat32(disk, 512)
            for name in ("/bin", "/case", "/out"):
                transfer(disk, "mkdir", name)
            transfer(disk, "import", "/bin/file_posix.elf", probe)
            guest = boot(disk, "file_posix")
            baseline = resources(guest)
            output = command(guest, "exec-driver /bin/file_posix.elf run",
                             b"kind=exited code=", timeout=120)
            if b"kind=exited code=0" not in output or b"FILE_POSIX_OK" not in output:
                raise AssertionError(output[-4000:])
            if b"[posix] FAILED" in output:
                raise AssertionError(output[-4000:])
            if resources(guest) != baseline:
                raise AssertionError("resources drifted after file posix probe")
            report["checks"].extend([
                "empty_path_and_intermediate_dotdot",
                "trailing_slash_does_not_unlink_file",
                "truncate_append_require_create",
                "ftruncate_preserves_offset_and_zero_fills",
                "seek_past_eof_preserves_length",
                "rename_replaces_file_and_rejects_descendant",
                "open_and_pipe_reuse_lowest_descriptors",
                "spawn_open_uses_spawn_time_cwd",
                "spawn_close_then_dup2_fails",
                "spawnp_trailing_slash_path_boundary",
                "resources_restored",
            ])
            command(guest, "sync", b"[files] sync=ok")
            guest.close()
            guest = None
            report["status"] = "passed"
    finally:
        if guest is not None:
            try:
                guest.close()
            except Exception:
                pass
    out = ROOT / "build/file_posix_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: {len(report['checks'])} file posix checks | build {report['build_id']}")


if __name__ == "__main__":
    main()
