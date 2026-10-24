# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""E02: exceptions, E820 physical pages, mapping, console, and symbol debugging."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from toolchain import COMMON_FLAGS, LOCK, tool
from boot_smoke import Guest


def run_logged(command, name):
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=30)
    (ROOT / "build" / name).write_text(result.stdout)
    if result.returncode:
        raise AssertionError(f"{name}: command exited {result.returncode}: {result.stdout}")
    return result.stdout


def send_bytes(guest, data):
    # The kernel UART is polled; pacing avoids overrunning the single byte path.
    for value in data:
        guest.process.stdin.write(bytes([value]))
        guest.process.stdin.flush()
        time.sleep(0.004)


def send_command(guest, command, expected, timeout=10):
    start = len(guest.output)
    send_bytes(guest, command + b"\r")
    guest.expect(expected, start=start, timeout=timeout)
    guest.expect(b"xos64> ", start=start, timeout=timeout)
    return start


def expect_panic(guest, command, vector, name, timeout=10):
    guest.expect(b"xos64> ", timeout=15)
    start = len(guest.output)
    send_bytes(guest, command + b"\r")
    guest.expect(f"[panic] vector={vector} {name}".encode(), start=start, timeout=timeout)
    guest.expect(b"[panic] result=halt", start=start, timeout=timeout)
    registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
    if "HLT=1" not in registers:
        raise AssertionError(f"{name}: CPU did not halt after panic")
    return bytes(guest.output)[start:]


def main():
    build = ROOT / "build"
    manifest = json.loads((build / "manifest.json").read_text())
    checks = []
    report = {"build_id": manifest["build_id"], "checks": checks, "status": "failed"}
    try:
        for relative, digest in manifest["sources"].items():
            if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
                raise AssertionError(f"Stale build: {relative}")
        for name, artifact in manifest["artifacts"].items():
            if hashlib.sha256((build / name).read_bytes()).hexdigest() != artifact["sha256"]:
                raise AssertionError(f"Artifact changed: {name}")
        report["image_sha256"] = manifest["artifacts"]["xos.img"]["sha256"]

        # Check the linked result, rather than relying solely on compiler flags.
        elf = (build / "kernel.elf").read_bytes()
        if elf[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<HH", elf, 16) != (2, 62):
            raise AssertionError("Kernel is not little-endian ELF64 x86-64 ET_EXEC")
        phoff = struct.unpack_from("<Q", elf, 32)[0]
        phsize, phcount = struct.unpack_from("<HH", elf, 54)
        loads = []
        for i in range(phcount):
            kind, flags = struct.unpack_from("<II", elf, phoff + i * phsize)
            if kind in (2, 3):
                raise AssertionError("Unexpected dynamic loader/linking")
            if kind == 1:
                if flags & 3 == 3:
                    raise AssertionError("Writable executable ELF segment")
                loads.append(flags)
        if sorted(loads) != [4, 5, 6]:
            raise AssertionError(f"Unexpected kernel segments: {loads}")
        sections = (build / "kernel_elf.log").read_text()
        for section in (".init_array", ".fini_array", ".tdata", ".tbss", ".dynamic", ".interp"):
            if section in sections:
                raise AssertionError(f"Unsupported runtime section: {section}")
        disassembly = (build / "kernel_disassembly.log").read_text()
        if re.search(r"\b(?:[xyz]mm\d+|mm[0-7]|st\([0-7]\))\b", disassembly):
            raise AssertionError("Unexpected FP/SIMD registers in kernel")
        checks.append("elf_static_rx_r_rw_no_implicit_runtime_or_simd")

        from run_qemu import qemu_command
        qemu_version = subprocess.check_output([qemu_command(build / "xos.img")[0], "--version"],
                                               text=True).splitlines()[0]
        if qemu_version != "QEMU emulator version " + LOCK["qemu"]:
            raise AssertionError(f"Unpinned QEMU: {qemu_version}")
        report["qemu"] = qemu_version

        symbols = manifest["symbols"]
        guest = Guest(build / "xos.img", "kernel_smoke")
        report["command"] = guest.command
        try:
            guest.expect(b"arch=x86_64 build=" + manifest["build_id"].encode())
            guest.expect(b"event=boot_info_valid memory_map=complete")
            guest.expect(b"event=runtime_checked bss=zero data=valid")
            guest.expect(b"[cpu] event=exceptions_ready idt=0x")
            guest.expect(b"[mem] event=initialized usable_kib=")
            guest.expect(b"[vm] event=self_check result=pass")
            guest.expect(b"[boot] result=ready stage=E04")
            guest.expect(b"xos64> ", timeout=15)
            if manifest["configuration"]["easter_eggs"]:
                guest.expect(b"The underscores made it to 64 bits.")
                guest.expect(b"Guest star: Guo YePeng (did not panic, yet)")
            checks.append("bios_to_cpp_long_mode_bss_data_boot_info")

            output = bytes(guest.output)
            memory = re.search(rb"usable_kib=(\d+) managed_kib=(\d+) pages=(\d+) "
                               rb"free_pages=(\d+)", output)
            if memory is None:
                raise AssertionError("Missing memory summary fields")
            usable_kib, managed_kib, pages, free_pages = (int(value) for value in memory.groups())
            if usable_kib < 500 * 1024 or managed_kib < 500 * 1024:
                raise AssertionError("E820 reported less RAM than the fixed QEMU configuration")
            if pages < 125 * 1024 or free_pages < 125 * 1024:
                raise AssertionError("Physical page manager did not adopt usable RAM")

            idt = re.search(rb"idt=0x([0-9a-f]{16})", output)
            if idt is None:
                raise AssertionError("Missing IDT base")
            idt_base = int(idt.group(1), 16)
            if not symbols["kernel_start"] <= idt_base < symbols["kernel_end"]:
                raise AssertionError("IDT is not inside the kernel image")
            guest.qmp("pmemsave", {"val": idt_base, "size": 256,
                                   "filename": str(build / "kernel_idt.bin")})
            idt_bytes = (build / "kernel_idt.bin").read_bytes()
            entry = idt_bytes[8 * 16:9 * 16]
            attributes = entry[5]
            if not attributes & 0x80 or attributes & 0x0f != 0x0e or entry[4] != 1:
                raise AssertionError("Double fault gate lacks present interrupt gate or IST1")
            nmi = idt_bytes[2 * 16:3 * 16]
            if not nmi[5] & 0x80 or nmi[4] != 2:
                raise AssertionError("NMI gate lacks IST2")
            checks.append("idt_exception_gates_and_double_fault_ist")

            start = send_command(guest, b"mem", b"[mem] usable_kib=")
            if b"[mem] window=0x0000000000100000.." not in bytes(guest.output)[start:]:
                raise AssertionError("Memory window does not start at the reserved low end")
            checks.append("debug_console_memory_report")

            if manifest["configuration"]["easter_eggs"]:
                send_command(guest, b"guo", b'[guo] name="Guo YePeng"')
                send_command(guest, b"joke", b"[joke] ")
                send_command(guest, b"about", b"Guo YePeng is in the credits")
                checks.append("easter_egg_banner_and_guo_commands")

            start = send_command(guest, b"alloc", b"alloc result=ok")
            allocated = re.search(rb"alloc result=ok phys=0x([0-9a-f]{16})",
                                  bytes(guest.output)[start:])
            if allocated is None:
                raise AssertionError("Missing allocation address")
            physical = int(allocated.group(1), 16)
            if physical % 4096 != 0 or physical < 0x100000:
                raise AssertionError("Allocator returned an invalid or reserved-low page")
            if physical >= 512 * 1024 * 1024:
                raise AssertionError("Allocator returned a page beyond configured RAM")
            if symbols["kernel_start"] <= physical < symbols["kernel_end"]:
                raise AssertionError("Allocator returned a page inside the kernel image")
            send_command(guest, b"free", b"free result=ok")
            send_command(guest, b"free", b"free result=invalid")
            checks.append("e820_physical_page_allocator_bounds_and_double_free")

            send_command(guest, b"vmtest", b"vmtest result=pass")
            checks.append("virtual_map_write_unmap_roundtrip")

            guest.qmp("pmemsave", {"val": 0x1000, "size": 0x5000,
                                   "filename": str(build / "bootstrap_page_tables.bin")})
            tables = (build / "bootstrap_page_tables.bin").read_bytes()
            leaves = struct.unpack_from("<1024Q", tables, 0x3000)
            if leaves[0] & 1:
                raise AssertionError("Null page mapped")
            for value in leaves:
                if value & 1 and value & 2 and not value >> 63:
                    raise AssertionError("Writable executable PTE")
            pdes = struct.unpack_from("<512Q", tables, 0x2000)
            for value in pdes[2:]:
                if value & 1 and not value >> 63:
                    raise AssertionError("Identity-extension page is executable")
            for address, writable, executable in (
                (symbols["kernel_entry"], False, True),
                (symbols["rodata_start"], False, False),
                (symbols["data_start"], True, False),
                (symbols["kernel_stack_bottom"], True, False),
            ):
                value = leaves[address // 4096]
                if bool(value & 2) != writable or bool(not value >> 63) != executable:
                    raise AssertionError(f"Wrong page permissions at {address:x}")
            checks.append("live_page_tables_null_guard_and_w_x")

            guest.qmp("screendump", {"filename": str(build / "kernel_screen.ppm")})
            start = len(guest.output)
            send_bytes(guest, b"halt\r")
            guest.expect(b"HALTED: CPU resting", start=start)
            time.sleep(0.1)
            registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
            (build / "kernel_registers.log").write_text(registers)
            cr0 = int(re.search(r"CR0=([0-9a-f]+)", registers)[1], 16)
            efer = int(re.search(r"EFER=([0-9a-f]+)", registers)[1], 16)
            if (cr0 & 0x80010001 != 0x80010001 or efer & 0xd00 != 0xd00 or
                    "CS64" not in registers or "HLT=1" not in registers or "A20=1" not in registers):
                raise AssertionError("Wrong execution mode, permissions, A20, or halt state")
            checks.append("debug_console_halt_reaches_cpu_hlt")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "pf")
        try:
            panic_output = expect_panic(guest, b"pf", 14, "page_fault")
            if b"cr2=0x00000000dead0000" not in panic_output:
                raise AssertionError("Page fault panic lacks the faulting CR2")
            if b"[panic] rip=0x" not in panic_output:
                raise AssertionError("Page fault panic lacks a RIP")
            (build / "fault_page.log").write_bytes(panic_output)
            checks.append("page_fault_panic_reports_rip_and_cr2")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "gp")
        try:
            panic_output = expect_panic(guest, b"gp", 13, "general_protection")
            if b"error=0x0000000000000182" not in panic_output:
                raise AssertionError("General protection panic lacks the selector error code")
            (build / "fault_gp.log").write_bytes(panic_output)
            checks.append("general_protection_panic_with_error_code")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "ud")
        try:
            (build / "fault_ud.log").write_bytes(
                expect_panic(guest, b"ud", 6, "invalid_opcode"))
            checks.append("invalid_opcode_panic")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "div")
        try:
            (build / "fault_div.log").write_bytes(
                expect_panic(guest, b"div", 0, "divide_error"))
            checks.append("divide_error_panic")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "df")
        try:
            (build / "fault_df.log").write_bytes(
                expect_panic(guest, b"df", 8, "double_fault"))
            checks.append("double_fault_panic_on_ist")
        finally:
            guest.close()

        guest = Guest(build / "xos.img", "no_nx", cpu="qemu64,-nx")
        try:
            guest.expect(b"BOOT_ERROR: cpu_requires_long_mode_nx_pae")
            registers = guest.qmp("human-monitor-command", {"command-line": "info registers"})
            if "HLT=1" not in registers or b"event=kernel_enter" in guest.output:
                raise AssertionError("Unsupported CPU not rejected")
            checks.append("unsupported_cpu_rejected_before_kernel")
        finally:
            guest.close()

        clang = shutil.which("clang++")
        if clang is None:
            raise AssertionError("clang++ required for host and cross-ISA verification")
        report["verification_clang"] = subprocess.check_output([clang, "--version"],
                                                               text=True).splitlines()[0]
        include = ["-I", str(ROOT / "src/kernel/include"), "-I", str(ROOT / "src/shared/include"), "-I", str(build)]
        host_test = str(build / "boot_info_cases")
        run_logged([clang, "-std=c++20", "-Wall", "-Wextra", "-Werror", *include,
                    str(ROOT / "tests/boot_info_cases.cpp"),
                    str(ROOT / "src/kernel/core/boot_info.cpp"), "-o", host_test],
                   "boot_info_cases_build.log")
        run_logged([host_test], "boot_info_cases.log")
        checks.append("normalized_boot_info_failure_boundaries")
        for source in sorted((ROOT / "src/kernel/core").glob("*.cpp")):
            run_logged([clang, "--target=aarch64-none-elf", *COMMON_FLAGS, *include,
                        "-c", str(source), "-o", str(build / (source.stem + "_aarch64.o"))],
                       source.stem + "_aarch64_compile.log")
        checks.append("all_common_cpp_compiles_for_second_isa")

        # Remote debugging against the actual VM; only listen on loopback.
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        guest = Guest(build / "xos.img", "symbol_debug", debug_port=port)
        try:
            deadline = time.monotonic() + 5
            while not Path(guest.qmp_path).exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            lldb = shutil.which("lldb")
            if lldb is None:
                raise AssertionError("LLDB required for symbol validation")
            report["lldb"] = subprocess.check_output([lldb, "--version"], text=True).splitlines()[0]
            script = build / "symbol_debug.lldb"
            script.write_text(
                f'target create --arch x86_64 "{build / "kernel.elf"}"\n'
                f'settings set target.source-map . "{ROOT}"\n'
                f'gdb-remote 127.0.0.1:{port}\n'
                'breakpoint set --name kernel_main\ncontinue\n'
                'bt\nframe variable info regions\nregister read rip rsp rdi rsi\n'
                'source list\nprocess detach\n')
            debug_log = run_logged([lldb, "--no-lldbinit", "--batch", "-s", str(script)],
                                   "symbol_debug.log")
            if ("stop reason = breakpoint" not in debug_log or "kernel_main.cpp:" not in debug_log
                    or "0x0000000000006800" not in debug_log or "kernel_entry" not in debug_log):
                raise AssertionError("Missing source breakpoint, argument, or symbolic stack")
            guest.expect(b"[boot] result=ready stage=E04")
            checks.append("lldb_source_breakpoint_arguments_and_symbolic_stack")
        finally:
            guest.close()
        report["status"] = "passed"
        print(f"PASS: {len(checks)} E02 checks | build {manifest['build_id']}")
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        (build / "kernel_smoke_report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
