"""E03: ring3 tasks, timer preemption, IPC, and user fault isolation."""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from boot_smoke import Guest


def pump(guest, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if guest.process.poll() is not None:
            raise AssertionError(f"QEMU exited {guest.process.returncode}")
        for key, _ in guest.selector.select(timeout=0.05):
            data = key.fileobj.read1(4096)
            if data:
                guest.output.extend(data)


def send_bytes(guest, data):
    for value in data:
        guest.process.stdin.write(bytes([value]))
        guest.process.stdin.flush()
        time.sleep(0.004)


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    guest = Guest(build / "xos.img", "task_smoke")
    report["command"] = guest.command
    try:
        guest.expect(b"xos64> ", timeout=20)
        guest.expect(b"[task] event=ready count=8")
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        guest.expect(b"[sched] event=start tasks=8", start=start)
        keep_start = len(guest.output)
        guest.expect(b"sup> ", start=keep_start, timeout=10)
        send_bytes(guest, b"demo keep\r")
        guest.expect(b"demo: keep", start=keep_start, timeout=8)
        guest.expect(b"sup> ", start=keep_start, timeout=8)
        checks.append("ring3_tasks_and_timer_started")

        pump(guest, 2.0)
        output = bytes(guest.output)[start:]
        if output.count(b"A") < 10:
            raise AssertionError(f"heartbeat did not survive the spinner: {output[-500:]!r}")
        checks.append("timer_preemption_keeps_heartbeat_alive")

        guest.expect(b"bad length", start=start, timeout=8)
        guest.expect(b"bad pointer", start=start, timeout=8)
        checks.append("ipc_bounds_and_user_pointer_rejected")
        guest.expect(b"ping", start=start, timeout=8)
        guest.expect(b"tx", start=start, timeout=8)
        checks.append("ipc_message_delivered_between_tasks")

        guest.expect(b"bad handle rejected", start=start, timeout=8)
        guest.expect(b"no send right", start=start, timeout=8)
        checks.append("invalid_ipc_handle_and_missing_right_rejected")

        guest.expect(b"bye", start=start, timeout=8)
        checks.append("user_exit_removed_from_run_queue")

        guest.expect(b"[task] event=reclaimed pid=5", start=start, timeout=8)
        guest.expect(b"[task] event=reclaimed pid=6", start=start, timeout=8)
        checks.append("dead_tasks_reclaimed")

        guest.expect(b"[task] event=fault pid=5 vector=14", start=start, timeout=8)
        guest.expect(b"cr2=0x0000000000100000", start=start, timeout=8)
        fault_output = bytes(guest.output)[start:]
        fault_at = fault_output.index(b"[task] event=fault pid=5")
        if fault_output[fault_at:].count(b"A") < 5:
            raise AssertionError("heartbeat stopped after the probe fault")
        checks.append("user_fault_isolated_to_probe")

        guest.expect(b"sup> ", start=start, timeout=10)
        ps_start = len(guest.output)
        send_bytes(guest, b"ps\r")
        guest.expect(b"pid=2 name=spinner", start=ps_start, timeout=8)
        guest.expect(b"sup> ", start=ps_start, timeout=8)
        checks.append("supervisor_terminal_lists_live_tasks")

        kill_start = len(guest.output)
        send_bytes(guest, b"kill 2\r")
        guest.expect(b"killed_by_supervisor pid=2", start=kill_start, timeout=8)
        guest.expect(b"[task] event=reclaimed pid=2", start=kill_start, timeout=8)
        guest.expect(b"sup> ", start=kill_start, timeout=8)
        pump(guest, 0.5)
        after_kill = bytes(guest.output)[kill_start:]
        if after_kill.count(b"A") < 3:
            raise AssertionError("heartbeat stopped after supervisor kill")
        checks.append("supervisor_kill_reclaims_target")

        second_ps = len(guest.output)
        send_bytes(guest, b"ps\r")
        guest.expect(b"sup> ", start=second_ps, timeout=8)
        if b"pid=2" in bytes(guest.output)[second_ps:]:
            raise AssertionError("killed task still listed by ps")
        checks.append("killed_task_removed_from_tasklist")

        cr3_values = set()
        saw_ring3 = False
        for _ in range(14):
            registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
            match = re.search(r"CR3=([0-9a-f]+)", registers)
            if match:
                cr3_values.add(match.group(1))
            if "CPL=3" in registers:
                saw_ring3 = True
            pump(guest, 0.12)
        if not saw_ring3:
            raise AssertionError("never observed CPL=3")
        if len(cr3_values) < 2:
            raise AssertionError(f"expected separate address spaces, saw CR3={cr3_values}")
        checks.append("per_task_address_spaces_observed")

        report["cr3_values"] = sorted(cr3_values)
        report["status"] = "passed"
        print(f"PASS: {len(checks)} E03 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        guest.close()
        (build / "task_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
