# SPDX-License-Identifier: Apache-2.0
"""Run two concurrent user processes through static TLS and C++ CRT lifecycles."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "tests")]
from boot_smoke import Guest
from e08_storage_smoke import boot
from make_work_disk import create_fat32
from process_smoke import command, resources
from task_smoke import send_bytes
from work_disk import transfer


def pump_until(guest, expected, start, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = bytes(guest.output)[start:]
        if b"[cpp_runtime] FAIL" in output:
            raise AssertionError(f"C++ runtime probe reported failure: {output[-1200:]!r}")
        if expected in output:
            return output
        if guest.process.poll() is not None:
            raise AssertionError(f"QEMU exited {guest.process.returncode}")
        for key, _ in guest.selector.select(timeout=0.1):
            data = key.fileobj.read1(4096)
            if data:
                guest.output.extend(data)
    raise AssertionError(f"Missing {expected!r}; output={bytes(guest.output)[start:][-1600:]!r}")


def spawn_worker(guest, worker_id, hold_ticks):
    start = len(guest.output)
    line = f"spawn-file /bin/cpp_runtime_probe.elf {worker_id} {hold_ticks}".encode() + b"\r"
    send_bytes(guest, line)
    output = pump_until(guest, b"[loader] started pid=", start, 15)
    pump_until(guest, b"sup> ", start, 15)
    output = bytes(guest.output)[start:]
    match = re.search(rb"\[loader\] started pid=(\d+)", output)
    if match is None:
        raise AssertionError(f"spawn did not report a PID: {output[-1000:]!r}")
    return int(match.group(1)), start


def await_ready(guest, worker_id, pid, start):
    marker = f"[cpp_runtime] ready id={worker_id} pid=".encode()
    complete_line = marker + str(pid).encode() + b" tls=ok\n"
    output = pump_until(guest, complete_line, start, 15)
    match = re.search(rb"\[cpp_runtime\] ready id=" + worker_id.encode() + rb" pid=(\d+) tls=ok\n", output)
    if match is None or int(match.group(1)) != pid:
        raise AssertionError(f"worker {worker_id} did not report its launched PID and TLS state: {output[-1000:]!r}")
    expected_order = (b"[cpp_runtime] preinit", b"[cpp_runtime] init", b"[cpp_runtime] global-ctor", marker)
    previous = -1
    for item in expected_order:
        position = output.find(item)
        if position <= previous:
            raise AssertionError(f"worker {worker_id} CRT startup order is wrong: {output[-1000:]!r}")
        previous = position
    return output


def check_tls_program_header(image):
    data = image.read_bytes()
    if len(data) < 64 or data[:4] != b"\x7fELF":
        raise AssertionError("C++ TLS probe is not an ELF image")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)
    tls_headers = []
    for index in range(phnum):
        fields = struct.unpack_from("<IIQQQQQQ", data, phoff + index * phentsize)
        kind, _, _, _, _, file_size, memory_size, alignment = fields
        if kind == 7:
            tls_headers.append((file_size, memory_size, alignment))
    if len(tls_headers) != 1:
        raise AssertionError(f"Expected one PT_TLS header, found {tls_headers}")
    file_size, memory_size, alignment = tls_headers[0]
    if file_size == 0 or memory_size <= file_size or memory_size <= 4096 or alignment < 64:
        raise AssertionError(f"PT_TLS does not cover initialized, zero-fill, alignment and multi-page cases: {tls_headers}")
    return {"file_size": file_size, "memory_size": memory_size, "alignment": alignment}


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    image = build / "user_cpp_runtime_probe.image.elf"
    if not image.is_file():
        raise SystemExit("Missing build/user_cpp_runtime_probe.image.elf; integrate and build the probe first")
    for source_name in ("src/user/programs/cpp_runtime_probe.cpp",
                        "src/user/libc/cpp_runtime.cpp",
                        "src/user/libc/main_entry.cpp"):
        expected = manifest.get("sources", {}).get(source_name)
        actual = hashlib.sha256((ROOT / source_name).read_bytes()).hexdigest()
        if expected != actual:
            raise SystemExit(f"Build does not include current {source_name}; rebuild before testing")
    report = {
        "build_id": manifest["build_id"],
        "system_image_sha256": manifest["artifacts"]["xos.img"]["sha256"],
        "probe_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "pt_tls": check_tls_program_header(image),
        "checks": [],
        "status": "failed",
    }
    guest = None
    try:
        with tempfile.TemporaryDirectory(prefix="xos_cpp_runtime_") as folder:
            disk = Path(folder) / "cpp_runtime.img"
            create_fat32(disk, 512)
            for path in ("/bin", "/tmp"):
                transfer(disk, "mkdir", path)
            transfer(disk, "import", "/bin/cpp_runtime_probe.elf", image)
            transfer(disk, "import", "/bin/runtime_probe.elf", build / "user_runtime_probe.image.elf")
            # Corrupt only PT_TLS in copies, preserving the valid program's LOADs.
            invalid_tls = []
            template = bytearray(image.read_bytes())
            phoff = struct.unpack_from("<Q", template, 32)[0]
            phsize, phnum = struct.unpack_from("<HH", template, 54)
            tls_at = next(phoff + i * phsize for i in range(phnum)
                          if struct.unpack_from("<I", template, phoff + i * phsize)[0] == 7)
            for name, field, value, reason in (
                ("tls_bad_length", 32, 0xffffffffffffffff, "bounds"),
                ("tls_bad_alignment", 48, 3, "alignment"),
                ("tls_too_large", 40, 0x100001, "too_large"),
                ("tls_wrong_template", 16, 0x40000000, "bounds"),
            ):
                data = bytearray(template)
                struct.pack_into("<Q", data, tls_at + field, value)
                path = Path(folder) / (name + ".elf")
                path.write_bytes(data)
                transfer(disk, "import", "/bin/" + name + ".elf", path)
                invalid_tls.append((name, reason))
            guest = boot(disk, "cpp_runtime_smoke")
            baseline = resources(guest)
            report["baseline_resources"] = baseline

            control = command(guest, "exec-driver /bin/runtime_probe.elf tls-control", b"kind=exited code=", timeout=30)
            if b"kind=exited code=0" not in control or b"tls-control=ok" not in control:
                raise AssertionError(control[-2000:])
            if resources(guest) != baseline:
                raise AssertionError("TLS rejected-control/abort leaked resources")
            report["checks"].append("tls_control_authorization_range_mapping_and_abort")
            for name, reason in invalid_tls:
                command(guest, "exec-file /bin/" + name + ".elf",
                        ("elf: rejected reason=" + reason).encode(), timeout=30)
                if resources(guest) != baseline:
                    raise AssertionError("malformed TLS changed task/page/completion baseline")
            report["checks"].append("malformed_tls_rejected_in_guest_without_resources")

            worker_pids = {}
            for worker_id in ("A", "B"):
                pid, start = spawn_worker(guest, worker_id, 500)
                worker_pids[worker_id] = pid
                await_ready(guest, worker_id, pid, start)
                report.setdefault("workers", {})[worker_id] = {"pid": pid}
            if b"[cpp_runtime] done id=A" in bytes(guest.output):
                raise AssertionError("first worker exited before the second worker became ready")
            for worker_id in ("A", "B"):
                if f"[cpp_runtime] exec-access id={worker_id} ok".encode() not in guest.output:
                    raise AssertionError("executable access cases did not complete")
            for worker_id in ("A", "B"):
                if f"[cpp_runtime] unwind id={worker_id} ok".encode() not in guest.output:
                    raise AssertionError("registered unwind frames missing")
            report["checks"].append("real_libgcc_backtrace_uses_registered_static_eh_frames")
            report["checks"].append("elf_directory_non_executable_missing_access_semantics")
            report["checks"].append("both_workers_ready_with_distinct_process_ids_before_wait")

            for worker_id in ("A", "B"):
                start = len(guest.output)
                send_bytes(guest, f"wait {worker_pids[worker_id]}\r".encode())
                output = pump_until(guest, b"kind=exited code=0", start, 20)
                pump_until(guest, b"sup> ", start, 20)
                if b"[cpp_runtime] FAIL" in output:
                    raise AssertionError(f"worker {worker_id} lost TLS while running: {output[-1200:]!r}")
            combined = bytes(guest.output)
            if b"[cpp_runtime] FAIL" in combined:
                raise AssertionError(f"TLS failure reported by worker: {combined[-1600:]!r}")
            for worker_id in ("A", "B"):
                done = f"[cpp_runtime] done id={worker_id}".encode()
                destructor = f"[cpp_runtime] global-dtor id={worker_id}".encode()
                fini = f"[cpp_runtime] fini id={worker_id}".encode()
                positions = [combined.find(marker) for marker in (done, destructor, fini)]
                if any(position < 0 for position in positions) or positions != sorted(positions):
                    raise AssertionError(f"worker {worker_id} did not exit through done, destructor, fini order")
            report["checks"].append("initialized_tbss_aligned_multi-page_tls_survives_yield_and_pit_per_worker")
            report["checks"].append("normal_exit_runs_global_destructor_before_reverse_fini_array")

            final_resources = resources(guest)
            report["final_resources"] = final_resources
            if final_resources != baseline:
                raise AssertionError(f"worker tasks/pages/completions leaked: {final_resources} != {baseline}")
            report["checks"].append("both_waited_workers_reclaim_tasks_pages_and_completion_records")
            report["status"] = "passed"
            print(f"PASS: {len(report['checks'])} C++ runtime groups | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (build / "cpp_runtime_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
