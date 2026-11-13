# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Build and export the small SDK; package user ELFs as immutable boot modules."""
import json
from pathlib import Path
import shutil
import struct
from toolchain import COMMON_FLAGS, X86_FLAGS, TARGET, tool
from ipc_v1_manifest import ipc_v1_manifest_entry
from device_manifest import device_manifest_entry
from archive_provenance import capture_build, copy_archive_provenance, digest


def build_users(root, build, nasm, run, build_id, terminal_supervisor_probe=False, ncurses_supervisor_probe=False):
    capture = capture_build(build, build_id, 'xos-source-declarations')
    sdk = build / "sdk"
    if sdk.is_symlink():
        raise SystemExit("Refusing a symlinked SDK output directory")
    if sdk.exists():
        shutil.rmtree(sdk)
    (sdk / "include/xos").mkdir(parents=True, exist_ok=True)
    (sdk / "lib").mkdir(exist_ok=True)
    newlib = root / "src/third_party/newlib/x86_64-elf"
    shutil.copytree(newlib / "include", sdk / "include", dirs_exist_ok=True)
    from newlib_patches import apply_patches
    apply_patches(sdk / "include", headers=True)
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
    shutil.copytree(root / "src/user/include/sys", sdk / "include/sys", dirs_exist_ok=True)
    # The XOS pthread surface (single-thread subset in the ordinary SDK, full
    # runtime in the threading SDK) is declared by the shared header, not newlib's.
    shutil.copyfile(root / "src/user/threading/include/pthread.h", sdk / "include/pthread.h")
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
        object_name = str(source.relative_to(root)).replace("\\", "_").replace("/", "_")
        obj = build / (object_name + ".o")
        isa_flags = [flag for flag in X86_FLAGS if source.name != "core_probe.cpp" or flag != "-mgeneral-regs-only"]
        run([*capture.launcher(), tool("g++"), *COMMON_FLAGS, *isa_flags, "-I", str(sdk / "include"),
             "-I", str(root / "src/third_party/fatfs"),
             "-I", str(root / "src/user/include"),
             "-I", str(source.parent),
             *extra, "-ffile-prefix-map=" + str(root) + "=.", "-c", str(source), "-o", str(obj)])
        return str(obj)

    sdk_objects = [compile_source(root / name) for name in (
        "src/user/sdk/text.cpp", "src/user/sdk/file_client.cpp", "src/user/sdk/terminal_client.cpp", "src/user/arch/x86_64/syscall.cpp", "src/shared/runtime/memory.cpp")]
    sdk_objects.extend(compile_source(source, ("-w", "-ffunction-sections", "-fdata-sections")
                                      if source.name == "newlib_syscalls.cpp" else ("-w",))
                       for source in sorted((root / "src/user/libc").glob("*.cpp")))
    thread_core = compile_source(root / "src/user/arch/x86_64/thread_core.cpp")
    core_archive = build / "threading_core/libxos_thread_core.a"
    core_archive.parent.mkdir(exist_ok=True)
    run([tool("ar"), "rcsD", str(core_archive), thread_core])
    capture.archive(core_archive)
    def compile_fatfs(source):
        object_name = str(source.relative_to(root)).replace("\\", "_").replace("/", "_")
        obj = build / (object_name + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-Os", "-w",
             "-I", str(sdk / "include"), "-I", str(root / "src/third_party/fatfs"),
             "-ffile-prefix-map=" + str(root) + "=.",
             "-c", str(source), "-o", str(obj)])
        return str(obj)

    fatfs_objects = [compile_fatfs(root / "src/third_party/fatfs/ff.c"),
                     compile_fatfs(root / "src/user/services/fatfs_diskio.cpp"),
                     compile_fatfs(root / "src/user/services/fatfs_unicode.cpp")]
    # The bundle installer grew this translation unit; keep -Os so the
    # file-backed install ISO stays within its size budget.
    file_ui_object = compile_source(root / "src/user/services/file_ui.cpp", ("-Os",))
    terminal_control_object = compile_source(root / "src/user/services/terminal_control.cpp")
    shell_terminal_object = compile_source(root / "src/user/services/shell_terminal.cpp")
    interactium_objects = [compile_source(root / "src/user/interactium" / name)
                          for name in ("window_manager.cpp", "service.cpp", "dispatcher.cpp",
                                       "service_loop.cpp", "ipc_transport.cpp")]
    archive = sdk / "lib/libxos.a"
    if archive.exists():
        archive.unlink()
    run([tool("ar"), "rcsD", str(archive), *sdk_objects])
    loader_objects = [compile_source(root / "src/user/loader" / name)
                      for name in ("elf.cpp", "load.cpp", "elf_cases.cpp", "command.cpp")]
    loader_objects.append(compile_source(root / "src/user/arch/x86_64/tls.cpp"))
    loader_archive = sdk / "lib/libxos_loader.a"
    run([tool("ar"), "rcsD", str(loader_archive), *loader_objects])
    archive_manifests = {}
    for built_archive in (archive, loader_archive):
        captured = capture.archive(built_archive)
        copied = copy_archive_provenance(captured, build, built_archive, sdk)
        archive_manifests[copied.relative_to(sdk).as_posix()] = digest(copied.read_bytes())
    names = ("supervisor", "files", "demo", "fault", "spin", "slow", "echo", "hello", "ipc_probe", "libc_hello", "e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe", "display", "gfxdemo", "interactium", "interactiumd", "ic_client", "xypm_recover", "xos_diag", "terminal", "terminal_app_probe", "audio_service", "audio_tone", "net_service")
    bootstrap_names = ("supervisor", "files")
    libc_programs = ("libc_hello", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "xos_diag", "terminal_app_probe")
    disk_programs = ("e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe", "xos_diag", "terminal", "terminal_app_probe")
    metadata = []
    header = ["#pragma once", "#include <xos/types.hpp>", "namespace xos::user_images {",
              "struct segment { u64 address, offset, files, memory; u32 permissions; };",
              "struct module { const char* name; const u8* bytes; u64 size; };"]
    for name in names:
        source_path = root / (f"src/user/services/{name}.cpp" if name in ("files", "display", "terminal") else
                              "src/user/programs/interactium_demo.cpp" if name == "interactium" else
                              "src/user/programs/interactium_service.cpp" if name == "interactiumd" else
                              "src/user/programs/interactium_client.cpp" if name == "ic_client" else
                              "src/user/programs/ipc_endpoint_probe.cpp" if name == "ipc_probe" else
                              f"src/user/programs/{name}.cpp")
        if name == "supervisor" and terminal_supervisor_probe:
            source_path = root / "tests/fixtures/ncursesw/terminal_supervisor_probe.cpp"
        if name == "supervisor" and ncurses_supervisor_probe:
            source_path = root / "tests/fixtures/ncursesw/ncurses_supervisor_probe.cpp"
        if name == "threading_core_probe":
            source_path = root / "tests/fixtures/threading/core_probe.cpp"
        if name == "terminal_app_probe":
            source_path = root / "tests/fixtures/ncursesw/terminal_app_probe.cpp"
        extra_flags = ("-w",) if name in libc_programs else ()
        if name == "supervisor":
            # Keep the embedded supervisor compact after the bundle installer
            # additions.
            extra_flags += ("-Os",)
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
             *(["-Wl,--gc-sections"] if name == "libc_hello" else []),
             "-T", str(sdk / "user.ld"), str(sdk / ("crt0_posix.o" if name in ("runtime_probe", "cpp_runtime_probe", "tls_exit_probe") else "crt0_libc.o" if name in libc_programs else "crt0.o")), main,
             *([str(loader_archive)] if name in ("supervisor", "xos_diag") else []), *fault_objects,
             *([str(core_archive), str(loader_archive)] if name in ("threading_core_probe", "gfxdemo", "terminal") else []),
             *([compile_source(root / "src/user/drivers/uart_16550.cpp")] if name == "terminal" else []),
             *([compile_source(root / "src/user/drivers/virtio_net.cpp")] if name == "net_service" else []),
                     *([compile_source(root / "src/user/drivers/pc_speaker.cpp")] if name == "audio_tone" else []),
             *([file_ui_object, terminal_control_object, shell_terminal_object] if name == "supervisor" else []),
             *([str(loader_archive)] if name == "supervisor" else []),
                     *([str(loader_archive)] if name == "audio_service" else []),
             *([*interactium_objects] if name in ("interactium", "interactiumd") else []),
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
        "archive_provenance": {"version": 1, "manifests": archive_manifests,
            "legacy_archives": {"lib/" + name: digest((sdk / "lib" / name).read_bytes())
                                for name in ("libc.a", "libm.a")}},
        "configuration": TARGET, "runtime_model": "single",
        "display_extensions": {"version": 1, "syscalls": [65, 66], "pixel_format": "XRGB8888", "surface_count": 1},
        "vm_extensions": {"version": 1, "syscall": 67, "status": "implemented_unqualified"},
        "cpu_time": {"version": 1, "syscall": 89, "status": "implemented_unqualified",
                     "unit": "nanoseconds", "scope": ["process", "current_thread", "waited_children"]},
        "ipc_v1": ipc_v1_manifest_entry(),
        "device_authorization": device_manifest_entry(),
        "diagnostic_extensions": {"fault_bundle_format": 1, "loader_receipt": "sha256-held-instance",
                                  "diagnostic_shell_command": "diag"},
        "file_identity": {"version": 1, "wire_version": 2, "status": "implemented_unverified",
                          "cwd_operations": [26, 27, 28], "directory_flag": 1024, "pin_flag": 2048},
        "process_extensions": {"syscalls": [*range(54, 62), *range(80, 87)], "file_operations": list(range(20, 29)),
            "startup_versions": [1, 2, 3], "exec_image_abi": 3, "exec_marker": ".xos.exec",
            "fork_supported": True, "exec_supported": True, "single_main_thread_only": True,
            "max_fork_depth": 3, "replacement_reservations": 1, "fd_count": 32, "spawn_argument_bytes": 255,
            "exec_argument_bytes": 4095, "startup_bytes": 16384, "pipe_atomic_bytes": 4096,
            "pipe_wait_write_minimum": True, "pipe_wait_deadline": "implemented_unqualified",
            "stream_lease": {"syscall": 80, "status": "claim_unsupported"},
            "channel": {"syscall": 81, "status": "implemented_unqualified"},
            "pio_grant": {"syscall": 82, "status": "implemented_unqualified"},
            "irq_event": {"syscall": 83, "status": "implemented_unqualified"},
            "pipe_atomic_flag": "0x8000000000000000"},
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
