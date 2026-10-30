# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Build the BIOS x86-64 kernel and the retained real-mode exercise image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from toolchain import LOCK, TARGET, COMMON_FLAGS, X86_FLAGS, audit, tool, output
from user_build import build_users

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
SECTOR_SIZE = 512
STAGE_TWO_SECTORS = 16
IMAGE_SIZE = 1440 * 1024


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    global BUILD
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=BUILD)
    parser.add_argument("--capacity-probe", action="store_true",
                        help="link a verified 5 MiB read-only section for the ISO capacity gate")
    parser.add_argument("--clock-irq-probe", action="store_true",
                        help="link a test-only generic clock/IRQ audit command, excluded from default images")
    parser.add_argument("--gpu-dma-page-limit", type=int, default=512,
                        help="kernel VirtIO-GPU DMA page budget; low values are explicit fault profiles")
    parser.add_argument("--gpu-poll-limit", type=int, default=10000000,
                        help="bounded VirtIO-GPU completion polls; zero is an explicit timeout profile")
    args = parser.parse_args()
    if not 1 <= args.gpu_dma_page_limit <= 4096 or not 0 <= args.gpu_poll_limit <= 100000000:
        parser.error("invalid VirtIO-GPU diagnostic budget")
    gpu_config = {"dma_page_limit": args.gpu_dma_page_limit, "poll_limit": args.gpu_poll_limit}
    BUILD = args.output_dir.resolve()
    if BUILD != ROOT / "build" and ROOT / "build" not in BUILD.parents:
        raise SystemExit("output directory must be build/ or one of its subdirectories")
    if args.clean:
        # One fixed generated directory only. Never walk or clean the workspace.
        if BUILD.is_symlink():
            raise SystemExit("Refusing to clean a symlinked build directory")
        if BUILD.exists():
            shutil.rmtree(BUILD)
        return
    if BUILD.is_symlink():
        raise SystemExit("Refusing a symlinked build directory")
    nasm = shutil.which(os.environ.get("NASM", "nasm"))
    if not nasm:
        raise SystemExit("NASM not found; install it or set NASM=/path/to/nasm")
    BUILD.mkdir(parents=True, exist_ok=True)
    # Bind the relocated cross compiler to the exact selected target tools.
    # This environment belongs only to this build process, not native host tests.
    target_tools = BUILD / "target_tools"
    if target_tools.is_symlink():
        raise SystemExit("Refusing a symlinked target-tool directory")
    target_tools.mkdir(exist_ok=True)
    for name in ("as", "ld"):
        link = target_tools / name
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise SystemExit(f"Refusing to overwrite a non-symlink target tool: {link}")
        link.symlink_to(Path(tool(name)).resolve())
    os.environ["COMPILER_PATH"] = str(target_tools)
    versions = audit()
    if (TARGET["architecture"], TARGET["platform"], TARGET["firmware"]) != ("x86_64", "pc", "bios"):
        raise SystemExit("Only the x86_64 / PC / BIOS backend is implemented")
    sources = [ROOT / "Makefile", ROOT / "VERSION", ROOT / "LICENSE", ROOT / "NOTICE"]
    sources.extend(p for p in sorted((ROOT / "licenses").glob("*")) if p.is_file())
    for folder in ("src", "scripts", "tests", "config"):
        sources.extend(p for p in sorted((ROOT / folder).rglob("*"))
                       if p.suffix in (".asm", ".s", ".sh", ".inc", ".py", ".cpp", ".hpp", ".c", ".h", ".ld", ".json", ".lldb"))
    source_hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sources}
    source_digest = sha256(json.dumps({"sources": source_hashes, "capacity_probe": args.capacity_probe, "clock_irq_probe": args.clock_irq_probe, "virtio_gpu": gpu_config}, sort_keys=True).encode())
    build_id = source_digest[:16]
    eggs = int(TARGET["easter_eggs"])
    (BUILD / "build_info.inc").write_text(
        f'%define xos_build_id "{build_id}"\n%define xos_easter_eggs {eggs}\n')
    (BUILD / "build_info.hpp").write_text(
        f'#define XOS_BUILD_ID "{build_id}"\n#define XOS_EASTER_EGGS {eggs}\n#define XOS_CAPACITY_PROBE {int(args.capacity_probe)}\n#define XOS_CLOCK_IRQ_PROBE {int(args.clock_irq_probe)}\n')
    commands = []

    def run(command):
        commands.append(command)
        subprocess.run(command, check=True)

    user_artifacts = build_users(ROOT, BUILD, nasm, run, build_id)
    user_programs = ("heartbeat", "spinner", "receiver", "sender", "probe", "quitter")
    header = ["#pragma once", "#include <xos/types.hpp>", "namespace xos::user_blobs {"]
    for name in user_programs:
        blob = BUILD / f"user_{name}.bin"
        run([nasm, "-f", "bin", "-Wall", "-Wno-reloc-abs-dword", "-Werror",
             str(ROOT / f"src/user/demo/{name}.asm"), "-o", str(blob)])
        data = blob.read_bytes()
        values = ", ".join(f"0x{value:02x}" for value in data)
        header.append(f"inline constexpr xos::u8 {name}[] = {{ {values} }};")
        header.append(f"inline constexpr xos::u32 {name}_size = {len(data)};")
    header.append("}")
    (BUILD / "user_blobs.hpp").write_text("\n".join(header) + "\n")

    objects = []
    # Select implemented backends explicitly; never compile every ISA/platform.
    cpp_sources = []
    for folder in ("core", "arch/x86_64", "platform/pc"):
        cpp_sources.extend(sorted((ROOT / "src/kernel" / folder).glob("*.cpp")))
    cpp_sources.extend(sorted((ROOT / "src/shared/runtime").glob("*.cpp")))
    if args.clock_irq_probe:
        cpp_sources.append(ROOT / "tests/kernel/clock_irq_probe.cpp")
    for source in cpp_sources:
        obj = BUILD / (str(source.relative_to(ROOT)).replace("/", "_") + ".o")
        gpu_flags = ["-DXOS_VGPU_DMA_PAGE_LIMIT=" + str(args.gpu_dma_page_limit),
                     "-DXOS_VGPU_POLL_LIMIT=" + str(args.gpu_poll_limit)] if source.name == "virtio_gpu.cpp" else []
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, *gpu_flags,
             "-I", str(ROOT / "src/kernel/include"), "-I", str(ROOT / "src/kernel"),
             "-I", str(ROOT / "src/shared/include"),
             "-I", str(BUILD), "-ffile-prefix-map=" + str(ROOT) + "=.",
             "-c", str(source), "-o", str(obj)])
        objects.append(str(obj))
    entry = BUILD / "kernel_entry.o"
    # ELF entry uses deliberate PC-relative external references, resolved by ld.
    run([nasm, "-f", "elf64", "-g", "-F", "dwarf", "-Wall",
         "-Wno-reloc-rel-dword", "-Werror",
         str(ROOT / "src/kernel/arch/x86_64/entry.asm"), "-o", str(entry)])
    objects.insert(0, str(entry))
    interrupts = BUILD / "kernel_interrupts.o"
    run([nasm, "-f", "elf64", "-g", "-F", "dwarf", "-Wall",
         "-Wno-reloc-abs-qword", "-Wno-reloc-rel-dword", "-Werror",
         str(ROOT / "src/kernel/arch/x86_64/interrupts.asm"), "-o", str(interrupts)])
    objects.append(str(interrupts))
    if args.capacity_probe:
        probe = BUILD / "capacity_probe.asm"
        probe.write_text("section .rodata.capacity_probe align=4096\n"
                         "global capacity_probe_begin, capacity_probe_end\n"
                         "capacity_probe_begin:\n times 5242880 db 0xa5\ncapacity_probe_end:\n"
                         "section .note.GNU-stack noalloc noexec nowrite progbits\n")
        obj = BUILD / "capacity_probe.o"
        run([nasm, "-f", "elf64", str(probe), "-o", str(obj)])
        objects.append(str(obj))
    kernel = BUILD / "kernel.elf"
    run([tool("g++"), *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
         "-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
         "-Wl,-Map," + str(BUILD / "kernel.map"),
         "-T", str(ROOT / "src/kernel/arch/x86_64/kernel.ld"), *objects,
         "-o", str(kernel)])
    if output([tool("nm"), "-u", str(kernel)]):
        raise SystemExit("Unresolved kernel symbols")
    run([tool("objcopy"), "-O", "binary", str(kernel), str(BUILD / "kernel.bin")])
    raw_kernel = (BUILD / "kernel.bin").read_bytes()
    symbols = {}
    for line in output([tool("nm"), "-n", str(kernel)]).splitlines():
        fields = line.split()
        if len(fields) == 3:
            symbols[fields[2]] = int(fields[0], 16)
    if (symbols["kernel_start"] != TARGET["kernel_base"] or
            symbols["kernel_entry"] != TARGET["kernel_base"] or
            symbols["kernel_end"] - symbols["kernel_start"] > TARGET["kernel_max_memory_bytes"] or
            not 1 <= len(raw_kernel) <= TARGET["kernel_max_file_bytes"]):
        raise SystemExit("Kernel exceeds fixed bootstrap layout")
    layout = {
        "kernel_load_address": symbols["kernel_start"],
        "kernel_memory_end": symbols["kernel_end"],
        "kernel_rodata_start": symbols["rodata_start"],
        "kernel_data_start": symbols["data_start"],
        "kernel_file_bytes": len(raw_kernel),
        "kernel_disk_sectors": (len(raw_kernel) + 511) // 512,
        "iso_kernel_max_file_bytes": TARGET["kernel_max_file_bytes"],
        "iso_payload_address": TARGET["iso_payload_address"],
        "iso_payload_max_bytes": TARGET["iso_payload_max_bytes"],
    }
    (BUILD / "kernel_layout.inc").write_text("".join(
        f"%define {name} {value}\n" for name, value in layout.items()))
    for name in ("boot_sector", "stage_two", "kernel_loader"):
        run([
            # bin + ORG resolves absolute references for 16/32-bit mode transitions.
            nasm, "-f", "bin", "-Wall", "-Wno-reloc-abs-word",
            "-Wno-reloc-abs-dword", "-Werror",
            "-I", str(ROOT / "src/boot/x86") + "/",
            "-I", str(BUILD) + "/",
            "-l", str(BUILD / f"{name}.lst"),
            "-o", str(BUILD / f"{name}.bin"),
            str(ROOT / f"src/boot/x86/{name}.asm"),
        ])
    for name in ("boot_sector_iso", "kernel_loader_iso", "kernel_loader_iso_file"):
        run([
            nasm, "-f", "bin", "-Wall", "-Wno-reloc-abs-word",
            "-Wno-reloc-abs-dword", "-Werror",
            "-I", str(ROOT / "src/boot/x86") + "/",
            "-I", str(BUILD) + "/",
            "-l", str(BUILD / f"{name}.lst"),
            "-o", str(BUILD / f"{name}.bin"),
            str(ROOT / f"src/boot/x86/{name}.asm"),
        ])
    boot = (BUILD / "boot_sector.bin").read_bytes()
    if len(boot) != SECTOR_SIZE or boot[-2:] != b"\x55\xaa":
        raise SystemExit("Invalid boot sector size/signature")
    legacy_available = len(raw_kernel) <= 512 * 1024 and symbols["kernel_end"] <= 0x400000
    legacy_stages = [("stage_two", "real_mode.img")]
    if legacy_available:
        legacy_stages.append(("kernel_loader", "xos.img"))
    for stage_name, image_name in legacy_stages:
        stage = (BUILD / f"{stage_name}.bin").read_bytes()
        if not 6 <= len(stage) <= STAGE_TWO_SECTORS * SECTOR_SIZE:
            raise SystemExit(f"{stage_name} must fit in the 16-sector window")
        if stage[0] != 0xeb or stage[2:6] != b"XOS2":
            raise SystemExit(f"Invalid {stage_name} entry/header")
        image = bytearray(IMAGE_SIZE)
        image[:SECTOR_SIZE] = boot
        image[SECTOR_SIZE:SECTOR_SIZE + len(stage)] = stage
        if image_name == "xos.img":
            offset = (1 + STAGE_TWO_SECTORS) * SECTOR_SIZE
            image[offset:offset + len(raw_kernel)] = raw_kernel
        temporary = BUILD / (image_name + ".tmp")
        temporary.write_bytes(image)
        temporary.replace(BUILD / image_name)
    if legacy_available:
        run([sys.executable, str(ROOT / "scripts/make_iso.py"),
             "--boot", str(BUILD / "boot_sector_iso.bin"),
             "--loader", str(BUILD / "kernel_loader_iso.bin"),
             "--kernel", str(BUILD / "kernel.bin"),
             "--output", str(BUILD / "xos.iso")])
    else:
        # Never leave a stale small-kernel legacy image beside a large ISO build.
        for name in ("xos.img", "xos.iso"):
            (BUILD / name).unlink(missing_ok=True)
    empty = BUILD / "empty.bin"
    empty.write_bytes(b"")
    run([sys.executable, str(ROOT / "scripts/make_iso.py"),
         "--boot", str(BUILD / "boot_sector_iso.bin"),
         "--loader", str(BUILD / "kernel_loader_iso_file.bin"),
         "--kernel", str(empty),
         "--file", f"KERNEL.BIN={BUILD / 'kernel.bin'}",
         "--output", str(BUILD / "xos-install.iso")])
    for name, command in {
        "kernel_disassembly.log": [tool("objdump"), "-d", str(kernel)],
        "kernel_elf.log": [tool("readelf"), "-h", "-l", "-S", str(kernel)],
        "compiler_configuration.log": [tool("g++"), "-v"],
    }.items():
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=True)
        (BUILD / name).write_text(result.stdout)
    artifact_names = ["boot_sector.bin", "stage_two.bin", "kernel_loader.bin", "kernel.elf",
                      "kernel.bin", "boot_sector_iso.bin", "kernel_loader_iso.bin", "kernel_loader_iso_file.bin",
                      "xos-install.iso", "real_mode.img", *user_artifacts]
    if legacy_available:
        artifact_names.extend(("xos.img", "xos.iso"))
    artifact_names.extend(str(path.relative_to(BUILD)) for path in sorted((BUILD / "sdk").rglob("*"))
                          if path.is_file())
    manifest = {
        "build_id": build_id,
        "version": (ROOT / "VERSION").read_text().strip(), "source_sha256": source_digest,
        "capacity_probe": args.capacity_probe, "clock_irq_probe": args.clock_irq_probe, "virtio_gpu": gpu_config, "legacy_images_available": legacy_available,
        "sources": source_hashes,
        "sdk_directories": [p.relative_to(BUILD / "sdk").as_posix()
                            for p in sorted((BUILD / "sdk").rglob("*")) if p.is_dir()],
        "tools": versions, "toolchain": LOCK, "configuration": TARGET, "commands": commands,
        "kernel_layout": layout, "symbols": {k: symbols[k] for k in (
            "kernel_entry", "kernel_main", "kernel_start", "kernel_end", "bss_start",
            "bss_end", "kernel_stack_bottom", "kernel_stack_top", "rodata_start", "data_start")},
        "artifacts": {
            name: {"bytes": (BUILD / name).stat().st_size,
                   "sha256": sha256((BUILD / name).read_bytes())} for name in artifact_names
        },
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Built xos-install.iso + real_mode.img | {build_id} | kernel {len(raw_kernel)} bytes | legacy={legacy_available}")


if __name__ == "__main__":
    main()
