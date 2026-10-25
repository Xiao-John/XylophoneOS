# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Build and export the small SDK; package user ELFs as immutable boot modules."""
import json
from pathlib import Path
import shutil
import struct
from toolchain import COMMON_FLAGS, X86_FLAGS, tool


def build_users(root, build, nasm, run, build_id):
    sdk = build / "sdk"
    if sdk.is_symlink():
        raise SystemExit("Refusing a symlinked SDK output directory")
    if sdk.exists():
        shutil.rmtree(sdk)
    (sdk / "include/xos").mkdir(parents=True, exist_ok=True)
    (sdk / "lib").mkdir(exist_ok=True)
    newlib = root / "src/third_party/newlib/x86_64-elf"
    shutil.copytree(newlib / "include", sdk / "include", dirs_exist_ok=True)
    shutil.copyfile(newlib / "lib/libc.a", sdk / "lib/libc.a")
    shutil.copyfile(newlib / "lib/libm.a", sdk / "lib/libm.a")
    shutil.copyfile(root / "src/third_party/newlib/COPYING.NEWLIB", sdk / "COPYING.NEWLIB")
    for folder in ("src/shared/include/xos", "src/user/include/xos"):
        for header in sorted((root / folder).glob("*.hpp")):
            if header.name == "thread_core.hpp":
                continue  # T0 mechanism API is not part of the legacy libc SDK.
            shutil.copyfile(header, sdk / "include/xos" / header.name)
    for header in sorted((root / "src/user/include").glob("*.h")):
        shutil.copyfile(header, sdk / "include" / header.name)
    shutil.copyfile(root / "src/user/arch/x86_64/user.ld", sdk / "user.ld")
    shutil.copyfile(root / "LICENSE", sdk / "LICENSE")
    shutil.copyfile(root / "NOTICE", sdk / "NOTICE")
    shutil.copytree(root / "licenses", sdk / "licenses", dirs_exist_ok=True)
    shutil.copyfile(root / "src/third_party/newlib/COPYING.NEWLIB", sdk / "licenses/newlib.txt")
    run([nasm, "-f", "elf64", "-g", "-F", "dwarf", "-o", str(sdk / "crt0.o"),
         str(root / "src/user/arch/x86_64/start.asm")])

    for crt_name, define in (("crt0_libc.o", "XOS_LIBC"), ("crt0_posix.o", "XOS_POSIX_MAIN")):
        run([nasm, "-f", "elf64", "-g", "-F", "dwarf", "-D" + define + "=1",
             "-o", str(sdk / crt_name), str(root / "src/user/arch/x86_64/start.asm")])

    def compile_source(source, extra=()):
        obj = build / (str(source.relative_to(root)).replace("/", "_") + ".o")
        isa_flags = [flag for flag in X86_FLAGS if source.name != "core_probe.cpp" or flag != "-mgeneral-regs-only"]
        run([tool("g++"), *COMMON_FLAGS, *isa_flags, "-I", str(sdk / "include"),
             "-I", str(root / "src/third_party/fatfs"),
             "-I", str(root / "src/user/include"),
             *extra, "-ffile-prefix-map=" + str(root) + "=.", "-c", str(source), "-o", str(obj)])
        return str(obj)

    sdk_objects = [compile_source(root / name) for name in (
        "src/user/sdk/text.cpp", "src/user/sdk/file_client.cpp", "src/user/arch/x86_64/syscall.cpp", "src/shared/runtime/memory.cpp")]
    sdk_objects.extend(compile_source(source, ("-w",)) for source in sorted((root / "src/user/libc").glob("*.cpp")))
    thread_core = compile_source(root / "src/user/arch/x86_64/thread_core.cpp")
    core_archive = build / "threading_core/libxos_thread_core.a"
    core_archive.parent.mkdir(exist_ok=True)
    run([tool("ar"), "rcsD", str(core_archive), thread_core])
    def compile_fatfs(source):
        obj = build / (str(source.relative_to(root)).replace("/", "_") + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-Os", "-w",
             "-I", str(sdk / "include"), "-I", str(root / "src/third_party/fatfs"),
             "-ffile-prefix-map=" + str(root) + "=.",
             "-c", str(source), "-o", str(obj)])
        return str(obj)

    fatfs_objects = [compile_fatfs(root / "src/third_party/fatfs/ff.c"),
                     compile_fatfs(root / "src/user/services/fatfs_diskio.cpp"),
                     compile_fatfs(root / "src/user/services/fatfs_unicode.cpp")]
    file_ui_object = compile_source(root / "src/user/services/file_ui.cpp")
    archive = sdk / "lib/libxos.a"
    if archive.exists():
        archive.unlink()
    run([tool("ar"), "rcsD", str(archive), *sdk_objects])
    loader_objects = [compile_source(root / "src/user/loader" / name)
                      for name in ("elf.cpp", "load.cpp", "elf_cases.cpp", "command.cpp")]
    loader_objects.append(compile_source(root / "src/user/arch/x86_64/tls.cpp"))
    loader_archive = sdk / "lib/libxos_loader.a"
    run([tool("ar"), "rcsD", str(loader_archive), *loader_objects])
    names = ("supervisor", "files", "demo", "fault", "spin", "slow", "echo", "hello", "libc_hello", "e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe")
    bootstrap_names = ("supervisor", "files")
    libc_programs = ("libc_hello", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe")
    disk_programs = ("e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe")
    metadata = []
    header = ["#pragma once", "#include <xos/types.hpp>", "namespace xos::user_images {",
              "struct segment { u64 address, offset, files, memory; u32 permissions; };",
              "struct module { const char* name; const u8* bytes; u64 size; };"]
    for name in names:
        source_path = root / (f"src/user/services/{name}.cpp" if name == "files" else f"src/user/programs/{name}.cpp")
        if name == "threading_core_probe":
            source_path = root / "tests/fixtures/threading/core_probe.cpp"
        extra_flags = ("-w",) if name in libc_programs else ()
        if name in ("cpp_runtime_probe", "tls_exit_probe"):
            extra_flags += ("-fuse-cxa-atexit", "-ftls-model=local-exec",
                            "-funwind-tables", "-fasynchronous-unwind-tables",
                            "-fno-optimize-sibling-calls")
        if name == "threading_core_probe":
            extra_flags += ("-ftls-model=local-exec",)
        main = compile_source(source_path, extra_flags)
        fault_objects = [compile_source(root / "src/user/arch/x86_64/fault_test.cpp")] if name == "fault" else []
        executable = build / f"user_{name}.elf"
        run([tool("g++"), *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
             "-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
             "-T", str(sdk / "user.ld"), str(sdk / ("crt0_posix.o" if name in ("runtime_probe", "cpp_runtime_probe", "tls_exit_probe") else "crt0_libc.o" if name in libc_programs else "crt0.o")), main,
             *([str(loader_archive)] if name == "supervisor" else []), *fault_objects,
             *([str(core_archive), str(loader_archive)] if name == "threading_core_probe" else []),
             *([file_ui_object] if name == "supervisor" else []),
             *([*fatfs_objects] if name == "files" else []),
             *(["-Wl,--start-group", str(archive), str(loader_archive), "-L", str(sdk / "lib"),
                "-lc", "-lm", "-lgcc", "-Wl,--end-group"]
               if name in libc_programs else [str(archive)]),
             "-o", str(executable)])
        image = build / f"user_{name}.image.elf"
        run([tool("objcopy"), "--strip-debug", str(executable), str(image)])
        data = image.read_bytes()
        if name not in disk_programs and len(data) > 131072:
            raise SystemExit(f"User ELF {name} exceeds image read limit")
        if name not in disk_programs:
            values = ",".join(f"0x{value:02x}" for value in data)
            header.append(f"inline constexpr u8 {name}[] = {{ {values} }};")
        segments = []
        phoff = struct.unpack_from("<Q", data, 32)[0]
        phsize, phcount = struct.unpack_from("<HH", data, 54)
        for i in range(phcount):
            fields = struct.unpack_from("<IIQQQQQQ", data, phoff + phsize * i)
            kind, flags, offset, address, _, file_bytes, memory_bytes, _ = fields
            if kind == 1 and memory_bytes:
                if flags & 3 == 3 or address < 0x40000000 or address + memory_bytes >= 0x7fff0000:
                    raise SystemExit(f"Invalid trusted bootstrap segment in {name}")
                segments.append((address, offset, file_bytes, memory_bytes, flags))
        entry = struct.unpack_from("<Q", data, 24)[0]
        if name in bootstrap_names:
            suffix = "" if name == "supervisor" else "_" + name
            header.append(f"inline constexpr segment bootstrap_segments{suffix}[] = {{")
            for segment in segments:
                header.append("{" + ",".join(str(value) for value in segment) + "},")
            header.append("};")
            header.append(f"inline constexpr u64 bootstrap_entry{suffix} = {entry};")
        metadata.append({"name": name, "entry": entry, "segments": segments,
                         "file": str(image.relative_to(build)), "bytes": len(data)})
    fixtures = []
    original = (build / "user_demo.image.elf").read_bytes()
    for name in ("bad_magic", "bad_interp", "bad_overflow"):
        data = bytearray(original)
        phoff = struct.unpack_from("<Q", data, 32)[0]
        if name == "bad_magic":
            data[0] = 0
        elif name == "bad_interp":
            struct.pack_into("<I", data, phoff, 3)
        else:
            struct.pack_into("<Q", data, phoff + 8, 0xffffffffffffffff)
        image = build / f"user_{name}.image.elf"
        image.write_bytes(data)
        header.append(f"inline constexpr u8 {name}[] = {{ " + ",".join(f"0x{v:02x}" for v in data) + " };")
        fixtures.append(str(image.relative_to(build)))
    header.append("inline constexpr module catalog[] = {")
    for name in names:
        if name in (*bootstrap_names, *disk_programs):  # disk-only probe never bloats bootstrap
            continue
        header.append(f'{{"{name}", {name}, sizeof({name})}},')
    for name in ("bad_magic", "bad_interp", "bad_overflow"):
        header.append(f'{{"{name}", {name}, sizeof({name})}},')
    header += ["};", "}"]
    (build / "user_images.hpp").write_text("\n".join(header) + "\n")
    (build / "user_images.json").write_text(json.dumps(metadata, indent=2) + "\n")
    import hashlib
    def sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    (sdk / "manifest.json").write_text(json.dumps({
        "build_id": build_id, "abi": 1, "target": "x86_64-elf",
        "process_extensions": {"syscalls": list(range(54, 62)), "file_operations": [20, 21, 22],
            "startup_versions": [1, 2, 3], "exec_image_abi": 3, "exec_marker": ".xos.exec",
            "fork_supported": True, "exec_supported": True, "single_main_thread_only": True,
            "max_fork_depth": 3, "replacement_reservations": 1, "fd_count": 32, "spawn_argument_bytes": 255,
            "exec_argument_bytes": 4095, "startup_bytes": 16384},
        "licenses": {
            str(path.relative_to(sdk)): sha256(path)
            for path in [sdk / "LICENSE", sdk / "NOTICE", *sorted((sdk / "licenses").glob("*"))]
            if path.is_file()
        },
        "libc": {"name": "newlib", "version": "4.6.0.20260123",
                 "libc_sha256": sha256(sdk / "lib/libc.a"),
                 "libm_sha256": sha256(sdk / "lib/libm.a")},
    }, indent=2) + "\n")
    return [f"user_{name}{suffix}.elf" for name in names for suffix in ("", ".image")] + fixtures
