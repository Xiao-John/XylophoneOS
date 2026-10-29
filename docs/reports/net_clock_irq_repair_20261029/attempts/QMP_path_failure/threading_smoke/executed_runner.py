# SPDX-License-Identifier: Apache-2.0
"""Run T0/T1 probes inside XOS, on a private boot image and FAT32 disk."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/final_runs/threading_smoke')
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from make_work_disk import create_fat32
from work_disk import transfer
from process_smoke import command, resources
from task_smoke import send_bytes, pump


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    report = {"build_id": manifest["build_id"], "status": "failed", "checks": [],
              "scope": "T0/T1 mechanism probes; T2 newlib/pthread/C++ not qualified", "runs": []}
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_threading_") as folder:
            private = Path(folder)
            image, disk = private / "boot.img", private / "work.img"
            shutil.copyfile(build / "xos.img", image)
            report["image_sha256"] = hashlib.sha256(image.read_bytes()).hexdigest()
            probe = build / "user_threading_core_probe.image.elf"
            report["probe_sha256"] = hashlib.sha256(probe.read_bytes()).hexdigest()
            create_fat32(disk, 512)
            transfer(disk, "mkdir", "/bin")
            transfer(disk, "import", "/bin/threading.elf", probe)
            transfer(disk, "import", "/bin/child.elf", build/"user_demo.image.elf")
            guest = Guest(image, "threading", work_disk=disk)
            guest.expect(b"xos64> ", timeout=30)
            send_bytes(guest, b"run\r")
            guest.expect_supervisor(trace=True, timeout=30)
            pump(guest, 1.5)
            baseline = resources(guest)
            report["resource_baseline"] = baseline
            for iteration in range(3):
                output = command(guest, "exec-file /bin/threading.elf core", b"kind=exited code=", timeout=60)
                assert b"[threading] shared stack tls fpu preempt prepare rollback join detach wait timeout pins=ok" in output, output[-3000:]
                assert b"kind=exited code=0" in output, output[-3000:]
                after = resources(guest)
                assert after == baseline, (baseline, after)
                report["runs"].append({"mode": "core", "iteration": iteration, "resources_after": after})
            report["checks"].append("guest_shared_memory_stack_static_tls_fpu_timer_preemption")
            report["checks"].append("guest_version_reserved_bad_output_entry_stack_tls_quota_abort_rollback")
            report["checks"].append("guest_join_value_unique_self_unknown_detach_and_reclaim")
            report["checks"].append("guest_wait_compare_deadline_wake_blocked_and_pinned_heap")
            output = command(guest, "exec-file /bin/threading.elf last", b"kind=exited code=", timeout=30)
            assert b"last-thread-cleanup" in output and b"kind=exited code=0" in output, output[-3000:]
            assert resources(guest) == baseline
            report["checks"].append("guest_main_thread_exit_last_worker_revokes_pending_reservation")
            output = command(guest, 'exec-file /bin/threading.elf arbitration', b'kind=exited code=', timeout=30)
            assert b'last-arbitration-stopped-peer=ok' in output and b'kind=exited code=0' in output, output[-3000:]
            assert resources(guest) == baseline
            report['checks'].append('guest_last_exit_waits_for_peer_preempted_between_begin_exit_and_thread_exit')
            output = command(guest, 'exec-driver /bin/threading.elf builder', b'kind=exited code=', timeout=30)
            assert b'worker-builder-child-survives-thread-exit=ok' in output and b'kind=exited code=0' in output, output[-3000:]
            assert resources(guest) == baseline
            report['checks'].append('guest_worker_inherits_process_authority_and_retains_child_on_thread_exit')
            output = command(guest, "exec-file /bin/threading.elf fault", b"kind=faulted", timeout=30)
            assert re.search(rb"event=fault pid=\d+ vector=14[^\r\n]* tid=\d+", output), output[-3000:]
            assert resources(guest) == baseline
            report["checks"].append("guest_worker_fault_stops_entire_process_and_reclaims")
            # Original ELF isolation cases run through the same user-space loader.
            output = command(guest, "exec fault", b"kind=faulted", timeout=30)
            assert resources(guest) == baseline
            report["checks"].append("guest_original_fault_isolation_supervisor_survives")
            command(guest, "filetest", b"[filetest] result=pass", timeout=30)
            command(guest, "sync", b"[files] sync=ok", timeout=30)
            assert resources(guest) == baseline
            report["checks"].append("guest_original_file_service_and_sync")
            output = command(guest, 'spawn-file /bin/threading.elf blocked', b'[threading] all-blocked', timeout=30)
            pid = int(re.search(rb'\[loader\] started pid=(\d+)', output).group(1))
            output = command(guest, 'exec-file /bin/threading.elf foreignwake', b'kind=exited code=', timeout=30)
            assert b'cross-process-same-address-private=ok' in output and b'kind=exited code=0' in output, output[-3000:]
            command(guest, f'kill {pid}', b'kill: accepted', timeout=30)
            command(guest, f'wait {pid}', b'kind=killed', timeout=30)
            assert resources(guest) == baseline
            report['checks'].extend(['guest_FIFO_unique_join_claim', 'guest_partial_prepare_real_ENOMEM_rollback',
                'guest_timeout_wake_same_tick_single_completion', 'guest_cross_process_same_VA_wait_keys',
                'guest_kill_removes_blocked_threads_and_wait_records'])
            report["status"] = "passed"
            print(f"PASS {len(report['checks'])} threading groups | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest:
            guest.close()
        (build / "threading_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
