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
            shutil.copyfile(header, sdk / "include/xos" / header.name)
    shutil.copyfile(root / "src/user/arch/x86_64/user.ld", sdk / "user.ld")
    shutil.copyfile(root / "LICENSE", sdk / "LICENSE")
    run([nasm, "-f", "elf64", "-g", "-F", "dwarf", "-o", str(sdk / "crt0.o"),
         str(root / "src/user/arch/x86_64/start.asm")])

    def compile_source(source, extra=()):
        obj = build / (str(source.relative_to(root)).replace("/", "_") + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-I", str(sdk / "include"),
             "-I", str(root / "src/third_party/fatfs"),
             *extra, "-ffile-prefix-map=" + str(root) + "=.", "-c", str(source), "-o", str(obj)])
        return str(obj)

    sdk_objects = [compile_source(root / name) for name in (
        "src/user/sdk/text.cpp", "src/user/sdk/file_client.cpp", "src/user/arch/x86_64/syscall.cpp", "src/shared/runtime/memory.cpp")]
    sdk_objects.append(compile_source(root / "src/user/libc/newlib_syscalls.cpp", ("-w",)))
    def compile_fatfs(source):
        obj = build / (str(source.relative_to(root)).replace("/", "_") + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-Os", "-w",
             "-I", str(sdk / "include"), "-I", str(root / "src/third_party/fatfs"),
             "-ffile-prefix-map=" + str(root) + "=.",
             "-c", str(source), "-o", str(obj)])
        return str(obj)

    fatfs_objects = [compile_fatfs(root / "src/third_party/fatfs/ff.c"),
                     compile_fatfs(root / "src/user/services/fatfs_diskio.cpp")]
    file_ui_object = compile_source(root / "src/user/services/file_ui.cpp")
    archive = sdk / "lib/libxos.a"
    if archive.exists():
        archive.unlink()
    run([tool("ar"), "rcsD", str(archive), *sdk_objects])
    loader_objects = [compile_source(root / "src/user/loader" / name)
                      for name in ("elf.cpp", "load.cpp", "elf_cases.cpp")]
    loader_archive = sdk / "lib/libxos_loader.a"
    run([tool("ar"), "rcsD", str(loader_archive), *loader_objects])
    names = ("supervisor", "files", "demo", "fault", "spin", "slow", "echo", "hello", "libc_hello")
    bootstrap_names = ("supervisor", "files")
    libc_programs = ("libc_hello",)
    metadata = []
    header = ["#pragma once", "#include <xos/types.hpp>", "namespace xos::user_images {",
              "struct segment { u64 address, offset, files, memory; u32 permissions; };",
              "struct module { const char* name; const u8* bytes; u64 size; };"]
    for name in names:
        source_path = root / (f"src/user/services/{name}.cpp" if name == "files" else f"src/user/programs/{name}.cpp")
        main = compile_source(source_path, ("-w",) if name in libc_programs else ())
        fault_objects = [compile_source(root / "src/user/arch/x86_64/fault_test.cpp")] if name == "fault" else []
        executable = build / f"user_{name}.elf"
        run([tool("g++"), *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
             "-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
             "-T", str(sdk / "user.ld"), str(sdk / "crt0.o"), main,
             *([str(loader_archive)] if name == "supervisor" else []), *fault_objects,
             *([file_ui_object] if name == "supervisor" else []),
             *([*fatfs_objects] if name == "files" else []),
             *(["-Wl,--start-group", str(archive), "-L", str(sdk / "lib"),
                "-lc", "-lm", "-lgcc", "-Wl,--end-group"]
               if name in libc_programs else [str(archive)]),
             "-o", str(executable)])
        image = build / f"user_{name}.image.elf"
        run([tool("objcopy"), "--strip-debug", str(executable), str(image)])
        data = image.read_bytes()
        if len(data) > 131072:
            raise SystemExit(f"User ELF {name} exceeds image read limit")
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
        if name in bootstrap_names:  # supervisor/files are not exec catalog entries
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
        "libc": {"name": "newlib", "version": "4.6.0.20260123",
                 "libc_sha256": sha256(sdk / "lib/libc.a"),
                 "libm_sha256": sha256(sdk / "lib/libm.a")},
    }, indent=2) + "\n")
    return [f"user_{name}{suffix}.elf" for name in names for suffix in ("", ".image")] + fixtures
