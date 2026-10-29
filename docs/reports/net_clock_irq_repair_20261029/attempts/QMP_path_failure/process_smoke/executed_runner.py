# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""E04: guest-side ELF loading, SDK, wait/status, handles, and exact reclamation."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import time

ROOT=Path('/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/final_runs/process_smoke')
sys.path.insert(0, str(ROOT / "scripts"))
from boot_smoke import Guest
from task_smoke import send_bytes, pump
from kernel_smoke import run_logged
from toolchain import COMMON_FLAGS, tool


def command(guest, line, expected, timeout=15):
    start = len(guest.output)
    send_bytes(guest, line.encode() + b"\r")
    guest.expect(expected, start=start, timeout=timeout)
    guest.expect(b"sup> ", start=start, timeout=timeout)
    return bytes(guest.output)[start:]


def resources(guest):
    output = command(guest, "stats", b"completions=")
    match = re.search(rb"\[resources\] free=(\d+) tasks=(\d+) completions=(\d+)", output)
    if match is None:
        raise AssertionError(f"Missing resource counters: {output!r}")
    return tuple(int(value) for value in match.groups())


def physical_table(guest, address, build):
    path = build / "process_page.bin"
    guest.qmp("pmemsave", {"val": address, "size": 4096, "filename": str(path)})
    return struct.unpack("<512Q", path.read_bytes())


def mapping(guest, cr3, address, build):
    levels = []
    table = cr3
    for shift in (39, 30, 21, 12):
        value = physical_table(guest, table, build)[(address >> shift) & 511]
        levels.append(value)
        if not value & 1:
            return None
        if shift != 12 and value & 128:
            raise AssertionError("Unexpected huge user mapping")
        table = value & 0x000ffffffffff000
    return {"physical": table, "user": all(value & 4 for value in levels),
            "write": all(value & 2 for value in levels),
            "execute": all(not value >> 63 for value in levels)}


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    report["image_sha256"] = manifest["artifacts"]["xos.img"]["sha256"]
    guest = None
    try:
        for name, digest in manifest["sources"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
                raise AssertionError(f"Source changed after build: {name}")
        for name, info in manifest["artifacts"].items():
            if hashlib.sha256((build / name).read_bytes()).hexdigest() != info["sha256"]:
                raise AssertionError(f"Artifact mismatch: {name}")
        clang = shutil.which("clang++")
        include = ["-I", str(ROOT / "src/shared/include"), "-I", str(ROOT / "src/user/include")]
        host = build / "elf_cases"
        run_logged([clang, "-std=c++20", "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                    *include, str(ROOT / "tests/elf_cases.cpp"),
                    str(ROOT / "src/user/loader/elf.cpp"), str(ROOT / "src/user/loader/elf_cases.cpp"),
                    "-o", str(host)], "elf_cases_build.log")
        run_logged([str(host), str(build / "user_demo.image.elf")], "elf_cases.log")
        checks.append("elf_boundary_cases_truncations_and_mutations_under_sanitizers")
        for folder in ("src/user/loader", "src/user/sdk", "src/shared/runtime"):
            for source in sorted((ROOT / folder).glob("*.cpp")):
                run_logged([clang, "--target=aarch64-none-elf", *COMMON_FLAGS, *include,
                            "-c", str(source), "-o", str(build / (source.stem + "_portable.o"))],
                           source.stem + "_portable.log")
        checks.append("loader_and_sdk_common_code_second_isa_compile")
        # E06 links newlib only into libc_hello; it intentionally uses SSE.
        for name in ("supervisor", "demo", "spin", "slow", "echo"):
            assembly = run_logged([tool("objdump"), "-d", str(build / f"user_{name}.image.elf")],
                                  f"user_{name}_disassembly.log")
            if re.search(r"\b(?:[xyz]mm\d+|mm[0-7]|fld\w*|fst\w*|fxsave\w*|xsave\w*)\b", assembly):
                raise AssertionError(f"Unsupported FP/SIMD in legacy SDK output: {name}")
        guest = Guest(build / "xos.img", "process_smoke")
        report["command"] = guest.command
        guest.expect(b"xos64> ", timeout=20)
        start = len(guest.output)
        send_bytes(guest, b"run\r")
        guest.expect_any((b"Welcome to Xshell", b"XOS E07 user loader"), start=start, timeout=15)
        guest.expect_supervisor(trace=True, start=start)
        command(guest, "demo keep", b"demo: keep")
        pump(guest, 0.2)
        # Keep the heartbeat and the non-yielding legacy spinner, reduce IPC log noise.
        command(guest, "kill 3", b"kill: accepted")
        command(guest, "kill 4", b"kill: accepted")
        baseline = resources(guest)
        report["baseline_resources"] = baseline
        images = command(guest, "images", b"image=echo")
        for name in (b"demo", b"fault", b"spin", b"slow", b"echo"):
            if b"image=" + name not in images:
                raise AssertionError("Missing user image")
        checks.append("gcc_cpp_sdk_programs_and_guest_image_catalog")

        demo = command(guest, "exec demo hello world", b"kind=exited code=42")
        for marker in (b"bss=zero data=valid argc=3", b"arg[0]=demo", b"arg[1]=hello",
                       b"arg[2]=world", b"stderr=valid", b"handles=checked create=denied"):
            if marker not in demo:
                raise AssertionError(f"Missing demo result {marker!r}")
        child = int(re.search(rb"\[loader\] started pid=(\d+)", demo)[1])
        command(guest, f"wait {child}", b"wait: error=-1")
        command(guest, "wait 1", b"wait: error=-1")
        if resources(guest) != baseline:
            raise AssertionError("Normal child or completion leaked resources")
        checks.append("elf_segments_bss_data_argv_handles_exit_and_single_consumption")

        slow = command(guest, "exec slow", b"kind=exited code=-7")
        if b"event=wait_blocked parent=7" not in slow or slow.count(b"A") < 2:
            raise AssertionError("Wait did not block while other tasks progressed")
        checks.append("blocking_wait_and_signed_exit_code_with_preemption")

        start = len(guest.output)
        send_bytes(guest, b"exec echo\r")
        guest.expect(b"[echo] input> ", start=start)
        send_bytes(guest, b"hello_from_stdin\r")
        guest.expect(b"[echo] done", start=start)
        guest.expect(b"kind=exited code=0", start=start)
        guest.expect(b"sup> ", start=start)
        checks.append("inherited_stdin_stdout_and_nonblocking_read")

        for name, reason in (("bad_magic", "header"), ("bad_interp", "unsupported"),
                             ("bad_overflow", "bounds")):
            output = command(guest, "exec " + name, b"exec: error=-2")
            if f"elf: rejected reason={reason}".encode() not in output or b"event=started" in output:
                raise AssertionError(f"Invalid ELF was not rejected: {name}")
        command(guest, "elftest", b"cases=24 result=pass resources=stable")
        if resources(guest) != baseline:
            raise AssertionError("Malformed ELF path allocated resources")
        checks.append("guest_loader_rejects_malformed_interp_overflow_and_24_boundaries")

        command(guest, "primtest", b"rollback=stable", timeout=120)
        if resources(guest) != baseline:
            raise AssertionError("Construction/abort/capacity rollback leaked pages")
        checks.append("kernel_builder_bounds_permissions_stale_handles_and_capacity_rollback")

        for mode, vector in (("", 14), ("readonly", 14), ("nx", 14)):
            output = command(guest, ("exec fault " + mode).strip(), b"kind=faulted code=0")
            if f"vector={vector}".encode() not in output:
                raise AssertionError(f"Unexpected fault for {mode}: {output!r}")
        # E06 enabled per-task SSE/x87 state; the old fldz probe now completes.
        output = command(guest, "exec fault fpu", b"kind=exited code=99")
        if b"vector=" in output:
            raise AssertionError(f"FPU probe still faulted: {output!r}")
        if resources(guest) != baseline:
            raise AssertionError("Faulted/FPU ELF processes leaked resources")
        checks.append("private_memory_readonly_nx_and_enabled_fpu_status")

        spin = command(guest, "spawn spin", b"[loader] started pid=")
        match = re.search(rb"\[process\] pid=(\d+) address_space=0x([0-9a-f]+)", spin)
        child, cr3 = int(match[1]), int(match[2], 16)
        report["loaded_spin"] = {"pid": child, "cr3": cr3}
        image = (build / "user_spin.image.elf").read_bytes()
        phoff = struct.unpack_from("<Q", image, 32)[0]
        phsize, phcount = struct.unpack_from("<HH", image, 54)
        for i in range(phcount):
            kind, flags, _, address, _, _, size, _ = struct.unpack_from("<IIQQQQQQ", image, phoff + i * phsize)
            if kind != 1 or size == 0:
                continue
            value = mapping(guest, cr3, address, build)
            if value is None or not value["user"] or value["write"] != bool(flags & 2) or value["execute"] != bool(flags & 1):
                raise AssertionError("Guest ELF page permissions differ from program header")
        stack = mapping(guest, cr3, 0x7ffff000, build)
        if not stack["user"] or not stack["write"] or stack["execute"]:
            raise AssertionError("Wrong initial stack permissions")
        if mapping(guest, cr3, 0x7ffdb000, build) is not None:
            raise AssertionError("Missing user stack guard")
        if mapping(guest, cr3, 0x100000, build)["user"]:
            raise AssertionError("Kernel page exposed to loaded ELF")
        checks.append("live_loaded_elf_permissions_stack_guard_and_kernel_isolation")
        command(guest, "ps", f"pid={child} name=spin".encode())
        command(guest, f"kill {child}", b"kill: accepted")
        command(guest, f"wait {child}", b"kind=killed code=-9")
        command(guest, f"wait {child}", b"wait: error=-1")
        if resources(guest) != baseline:
            raise AssertionError("Killed ELF process or wait record leaked")
        checks.append("background_spawn_supervisor_kill_and_distinct_killed_status")

        start = len(guest.output)
        send_bytes(guest, b"exec spin\r")
        guest.expect(b"[spin] alive", start=start)
        guest.expect(b"event=wait_blocked", start=start)
        send_bytes(guest, b"\x1b")
        guest.expect(b"event=cancelled_by_escape", start=start)
        guest.expect(b"kind=killed code=-27", start=start)
        guest.expect(b"sup> ", start=start)
        if resources(guest) != baseline:
            raise AssertionError("Foreground cancellation leaked resources")
        checks.append("foreground_infinite_loop_escape_recovers_terminal")

        repeats = []
        for _ in range(10):
            command(guest, "exec demo again", b"kind=exited code=42")
            repeats.append(resources(guest))
        if any(value != baseline for value in repeats):
            raise AssertionError(f"Repeated ELF execution leaked pages: {repeats}")
        report["repeated_resources"] = repeats
        checks.append("ten_repeated_load_wait_exit_cycles_exact_resource_stability")
        guest.qmp("screendump", {"filename": str(build / "process_screen.ppm")})
        report["status"] = "passed"
        print(f"PASS: {len(checks)} E04 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if guest is not None:
            guest.close()
        (build / "process_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
