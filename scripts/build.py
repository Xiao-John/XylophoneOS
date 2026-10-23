"""Build the BIOS x86-64 kernel and the retained real-mode exercise image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
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
    BUILD.mkdir(exist_ok=True)
    versions = audit()
    if (TARGET["architecture"], TARGET["platform"], TARGET["firmware"]) != ("x86_64", "pc", "bios"):
        raise SystemExit("Only the x86_64 / PC / BIOS backend is implemented")
    sources = [ROOT / "Makefile"]
    for folder in ("src", "scripts", "tests", "config"):
        sources.extend(p for p in sorted((ROOT / folder).rglob("*"))
                       if p.suffix in (".asm", ".inc", ".py", ".cpp", ".hpp", ".ld", ".json", ".lldb"))
    source_hashes = {str(p.relative_to(ROOT)): sha256(p.read_bytes()) for p in sources}
    source_digest = sha256(json.dumps(source_hashes, sort_keys=True).encode())
    build_id = source_digest[:16]
    eggs = int(TARGET["easter_eggs"])
    (BUILD / "build_info.inc").write_text(
        f'%define xos_build_id "{build_id}"\n%define xos_easter_eggs {eggs}\n')
    (BUILD / "build_info.hpp").write_text(
        f'#define XOS_BUILD_ID "{build_id}"\n#define XOS_EASTER_EGGS {eggs}\n')
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
    for source in cpp_sources:
        obj = BUILD / (str(source.relative_to(ROOT)).replace("/", "_") + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS,
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
    boot = (BUILD / "boot_sector.bin").read_bytes()
    if len(boot) != SECTOR_SIZE or boot[-2:] != b"\x55\xaa":
        raise SystemExit("Invalid boot sector size/signature")
    for stage_name, image_name in (("stage_two", "real_mode.img"), ("kernel_loader", "xos.img")):
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
    for name, command in {
        "kernel_disassembly.log": [tool("objdump"), "-d", str(kernel)],
        "kernel_elf.log": [tool("readelf"), "-h", "-l", "-S", str(kernel)],
        "compiler_configuration.log": [tool("g++"), "-v"],
    }.items():
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=True)
        (BUILD / name).write_text(result.stdout)
    artifact_names = ["boot_sector.bin", "stage_two.bin", "kernel_loader.bin", "kernel.elf",
                      "kernel.bin", "xos.img", "real_mode.img", *user_artifacts]
    artifact_names.extend(str(path.relative_to(BUILD)) for path in sorted((BUILD / "sdk").rglob("*"))
                          if path.is_file())
    manifest = {
        "build_id": build_id, "source_sha256": source_digest,
        "sources": source_hashes,
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
    print(f"Built xos.img + real_mode.img | {build_id} | kernel {len(raw_kernel)} bytes")


if __name__ == "__main__":
    main()
