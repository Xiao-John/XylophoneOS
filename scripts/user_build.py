# SPDX-License-Identifier: MIT AND Apache-2.0
# Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
"""Build and export the small SDK; package user ELFs as immutable boot modules."""
import json
from pathlib import Path
import shutil
import struct
from toolchain import COMMON_FLAGS, X86_FLAGS, TARGET, tool
from ipc_v1_manifest import ipc_v1_manifest_entry
from ipc_endpoint_manifest import ipc_endpoint_manifest_entry
from observation_manifest import observation_manifest_entry
from device_manifest import device_manifest_entry
from archive_provenance import capture_build, copy_archive_provenance, digest
from lwip_service_build import build as build_lwip_service


def build_users(root, build, nasm, run, build_id, terminal_supervisor_probe=False,
                ncurses_supervisor_probe=False, glibc_files_death_probe=False,
                files_private_storage_probe=False, files_private_client_probe=False, pumpkin_durable_probe=False,
                pumpkin_anchored_probe=False, pumpkin_native_login=False, pumpkin_user_login=False,
                pumpkin_user_resource=False, pumpkin_named_resource_store=False, pumpkin_provisioning_store=False,
                quiet_demos_on_launch=False, net_dns_probe=False, pumpkin_mobius=False,
                net_static_profile=None, pumpkin_deployment_realm=None, net_dhcp_profile=None,
                files_uncertain_probe=False, pumpkin_catalog_fixture=False,
                pumpkin_launch_probe=False, pumpkin_launch_storage_lease=False):
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
        for header in sorted(p for p in (root / folder).iterdir() if p.suffix in (".h", ".hpp")):
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
        "src/user/sdk/text.cpp", "src/user/sdk/file_client.cpp", "src/user/sdk/terminal_client.cpp",
        "src/user/sdk/launch_control.cpp", "src/user/arch/x86_64/syscall.cpp", "src/shared/runtime/memory.cpp")]
    sdk_objects.extend(compile_source(source) for source in sorted((root / "src/user/observation").glob("*.cpp")))
    sdk_objects.extend(compile_source(source, ("-w", "-ffunction-sections", "-fdata-sections")
                                      if source.name == "newlib_syscalls.cpp" else ("-w",))
                       for source in sorted((root / "src/user/libc").glob("*.cpp")))
    thread_core = compile_source(root / "src/user/arch/x86_64/thread_core.cpp")
    core_archive = build / "threading_core/libxos_thread_core.a"
    core_archive.parent.mkdir(exist_ok=True)
    run([tool("ar"), "rcsD", str(core_archive), thread_core])
    capture.archive(core_archive)
    def compile_fatfs(source, extra=()):
        object_name = str(source.relative_to(root)).replace("\\", "_").replace("/", "_")
        obj = build / (object_name + ".o")
        run([tool("g++"), *COMMON_FLAGS, *X86_FLAGS, "-Os", "-w", *extra,
             "-I", str(sdk / "include"), "-I", str(root / "src/third_party/fatfs"),
             "-ffile-prefix-map=" + str(root) + "=.",
             "-c", str(source), "-o", str(obj)])
        return str(obj)

    pumpkin_daemon_probe = pumpkin_durable_probe or pumpkin_anchored_probe
    files_slot_broker = files_private_client_probe or pumpkin_daemon_probe
    private_client_flags = ("-DXOS_FILES_PRIVATE_CLIENT_PROBE=1",) if files_slot_broker else ()
    durable_flags = ("-DXOS_PUMPKIN_DURABLE_PROBE=1",) if pumpkin_daemon_probe else ()
    if pumpkin_anchored_probe:
        durable_flags += ("-DXOS_PUMPKIN_ANCHORED_PROBE=1",)
    login_flags = ("-DXOS_PUMPKIN_NATIVE_LOGIN=1",) if pumpkin_native_login else ()
    if pumpkin_user_login:
        login_flags += ("-DXOS_PUMPKIN_USER_LOGIN=1",)
    if pumpkin_deployment_realm is not None:
        values = ",".join(f"0x{byte:02x}" for byte in bytes.fromhex(pumpkin_deployment_realm))
        login_flags += (f"-DXOS_PUMPKIN_DEPLOYMENT_REALM={values}",)
    if pumpkin_mobius:
        login_flags += ("-DXOS_PUMPKIN_MOBIUS=1", "-I", str(build))
    if pumpkin_user_resource:
        login_flags += ("-DXOS_PUMPKIN_USER_RESOURCE=1", "-DXOS_PUMPKIN_RESOURCE_BRIDGE=1")
    if pumpkin_named_resource_store:
        login_flags += ("-DXOS_PUMPKIN_NAMED_RESOURCE_STORE=1",)
    if pumpkin_provisioning_store:
        login_flags += ("-DXOS_PUMPKIN_PROVISIONING_STORE=1",)
    if pumpkin_catalog_fixture:
        login_flags += ("-DXOS_PUMPKIN_CATALOG_PROBE=1", "-I", str(build))
    if pumpkin_catalog_fixture or pumpkin_launch_probe:
        login_flags += ("-DXOS_PUMPKIN_LAUNCH_PROBE=1",)
    provisioning_flags = ("-DXOS_PUMPKIN_PROVISIONING_STORE=1",) if pumpkin_provisioning_store else ()
    durable_flags += login_flags
    private_storage_flags = (("-DXOS_FILES_PRIVATE_STORAGE_PROBE=1", *private_client_flags)
                             if files_private_storage_probe or files_slot_broker else ())
    private_storage_flags += provisioning_flags
    fatfs_objects = [compile_fatfs(root / "src/third_party/fatfs/ff.c"),
                     compile_fatfs(root / "src/user/services/fatfs_diskio.cpp", private_storage_flags),
                     compile_fatfs(root / "src/user/services/fatfs_unicode.cpp")]
    private_broker_objects = [compile_source(root / "src/user/services" / name, provisioning_flags) for name in
                              ("files_private_broker.cpp", "files_private_lease.cpp")] if files_slot_broker else []
    durable_objects = {}
    if pumpkin_daemon_probe:
        durable_objects = {name: compile_source(root / "src/user/pumpkin" / name,
                                          ("-Os", "-ffunction-sections", "-fdata-sections", *login_flags)) for name in
                           ("account_store.cpp", "service_core.cpp", "daemon_protocol.cpp", "native_ipc.cpp", "native_ipc_client.cpp")}
    if pumpkin_native_login:
        durable_objects.update({name: compile_source(root / "src/user/pumpkin" / name,
                                              ("-Os", "-ffunction-sections", "-fdata-sections", *login_flags)) for name in
                               ("native_login.cpp", "login_resource.cpp", "resource_dispatch.cpp", "sealed_blob.cpp")})
    if pumpkin_user_resource:
        durable_objects["resource_bridge.cpp"] = compile_source(root / "src/user/pumpkin/resource_bridge.cpp",
                                                                 ("-Os", "-ffunction-sections", "-fdata-sections", *login_flags))
    if pumpkin_named_resource_store:
        durable_objects.update({name: compile_source(root / "src/user/pumpkin" / name,
                                             ("-Os", "-ffunction-sections", "-fdata-sections")) for name in
                                ("named_resource_store.cpp", "named_resource_rpc.cpp")})
    if pumpkin_provisioning_store:
        durable_objects.update({name: compile_source(root / "src/user/pumpkin" / name,
                                             ("-Os", "-ffunction-sections", "-fdata-sections", *provisioning_flags))
                                for name in ("provisioning_store.cpp", "provisioning_protocol.cpp", "provisioning_client.cpp")})
    # The bundle installer grew this translation unit; keep -Os so the
    # file-backed install ISO stays within its size budget.
    file_ui_object = compile_source(root / "src/user/services/file_ui.cpp", ("-Os",))
    terminal_control_object = compile_source(root / "src/user/services/terminal_control.cpp")
    shell_terminal_object = compile_source(root / "src/user/services/shell_terminal.cpp")
    interactium_objects = [compile_source(root / "src/user/interactium" / name)
                          for name in ("window_manager.cpp", "service.cpp", "dispatcher.cpp",
                                       "service_loop.cpp", "ipc_transport.cpp")]
    net_objects, net_includes, net_configuration = build_lwip_service(root, build, sdk, run, tool, X86_FLAGS,
                                                                     net_dns_probe, net_static_profile, net_dhcp_profile)
    if net_configuration["enabled"]:
        net_objects += [compile_source(root / "src/user/network" / name,
                                      (*net_includes, "-Os", "-ffunction-sections", "-fdata-sections"))
                        for name in ("service_core.cpp", "lwip_stack.cpp", "service_loop.cpp",
                                     *(("dns_probe.cpp",) if net_dns_probe else ()),
                                     *(("dhcp_policy.cpp", "lwip_dhcp.cpp") if net_dhcp_profile else ()))]
    archive = sdk / "lib/libxos.a"
    if archive.exists():
        archive.unlink()
    run([tool("ar"), "rcsD", str(archive), *sdk_objects])
    loader_objects = [compile_source(root / "src/user/loader" / name)
                      for name in ("elf.cpp", "load.cpp", "elf_cases.cpp", "command.cpp",
                                   "glibc_d1/image_mapping.cpp", "glibc_d1/entry_stack.cpp",
                                   "glibc_d1/interpreter_entry.cpp", "dynamic/identity.cpp",
                                   "dynamic/generation.cpp", "dynamic/elf.cpp", "dynamic/closure.cpp",
                                   "dynamic/startup.cpp", "dynamic/authority.cpp", "dynamic/spawn.cpp")]
    loader_objects.append(compile_source(root / "src/user/arch/x86_64/tls.cpp"))
    loader_archive = sdk / "lib/libxos_loader.a"
    run([tool("ar"), "rcsD", str(loader_archive), *loader_objects])
    archive_manifests = {}
    for built_archive in (archive, loader_archive):
        captured = capture.archive(built_archive)
        copied = copy_archive_provenance(captured, build, built_archive, sdk)
        archive_manifests[copied.relative_to(sdk).as_posix()] = digest(copied.read_bytes())
    names = ("supervisor", "files", "demo", "fault", "spin", "slow", "echo", "hello", "ipc_probe", "libc_hello", "e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe", "display", "gfxdemo", "interactium", "interactiumd", "ic_client", "xypm_recover", "xos_diag", "terminal", "terminal_app_probe", "audio_service", "audio_tone", "net_service")
    if files_private_client_probe:
        names += ("p2_store_probe",)
    if pumpkin_daemon_probe:
        names += ("pumpkin_durable",)
    if pumpkin_durable_probe:
        names += ("p2_auth_probe",)
    if pumpkin_anchored_probe:
        names += ("p2_anchor_proxy",)
    if pumpkin_native_login:
        names += ("pumpkin_holder",)
    if pumpkin_user_resource:
        names += ("p2_sealed",)
    bootstrap_names = ("supervisor", "files")
    libc_programs = ("libc_hello", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "xos_diag", "terminal_app_probe")
    disk_programs = ("e08_probe", "runtime_probe", "cpp_runtime_probe", "tls_exit_probe", "threading_core_probe", "xos_diag", "terminal", "terminal_app_probe")
    if pumpkin_durable_probe:
        disk_programs += ("p2_auth_probe",)
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
        if name == "p2_store_probe":
            source_path = root / "tests/fixtures/pumpkin/files_private_client_guest.cpp"
        if name == "pumpkin_durable":
            source_path = root / "src/user/pumpkin/daemon_main.cpp"
        if name == "p2_anchor_proxy":
            source_path = root / "src/user/pumpkin/generation_proxy.cpp"
        if name == "pumpkin_holder":
            source_path = root / "src/user/pumpkin/login_holder_main.cpp"
        if name == "p2_sealed":
            source_path = root / "src/user/pumpkin/resource_broker_main.cpp"
        if name == "p2_auth_probe":
            source_path = root / "tests/fixtures/pumpkin/durable_dash_client.cpp"
        extra_flags = ("-w",) if name in libc_programs else ()
        if name == "supervisor":
            # Keep the embedded supervisor compact after the bundle installer
            # additions.
            extra_flags += ("-Os", *private_client_flags, *durable_flags)
            if quiet_demos_on_launch:
                extra_flags += ("-DXOS_QUIET_DEMOS_ON_LAUNCH=1",)
            if net_dns_probe:
                extra_flags += ("-DXOS_NET_DNS_PROBE=1",)
            installation_profile = net_dhcp_profile or net_static_profile
            if installation_profile:
                extra_flags += (f"-DXOS_NET_STATIC_INSTANCE={installation_profile['pci_instance']}u",)
        if name == "files" and files_uncertain_probe:
            extra_flags += ("-DXOS_FILES_UNCERTAIN_PROBE=1",)
        if name == "files" and glibc_files_death_probe:
            extra_flags += ("-DXOS_GLIBC_FILES_DEATH_PROBE=1",)
        if name == "files":
            extra_flags += private_storage_flags
            if pumpkin_mobius:
                extra_flags += ("-DXOS_FILES_PRIVATE_DESKTOP_LEASE=1",)
            if pumpkin_launch_storage_lease:
                extra_flags += ("-DXOS_FILES_PRIVATE_LAUNCH_LEASE=1",)
        if name in ("pumpkin_durable", "p2_auth_probe", "p2_anchor_proxy", "pumpkin_holder", "p2_sealed"):
            extra_flags += ("-Os", *durable_flags)
        if name == "net_service":
            extra_flags += ("-Os", "-ffunction-sections", "-fdata-sections")
            if net_configuration["enabled"]:
                extra_flags += ("-DXOS_NET_STACK=1",)
            if net_dns_probe:
                extra_flags += ("-DXOS_NET_DNS_PROBE=1",)
        if name in ("cpp_runtime_probe", "tls_exit_probe"):
            extra_flags += ("-fuse-cxa-atexit", "-ftls-model=local-exec",
                            "-funwind-tables", "-fasynchronous-unwind-tables",
                            "-fno-optimize-sibling-calls")
        if name == "threading_core_probe":
            extra_flags += ("-ftls-model=local-exec",)
        main = compile_source(source_path, extra_flags)
        fault_objects = [compile_source(root / "src/user/arch/x86_64/fault_test.cpp")] if name == "fault" else []
        executable = build / f"user_{name}.elf"
        durable_link = pumpkin_daemon_probe and name in (
            "supervisor", "pumpkin_durable", "p2_auth_probe", "pumpkin_holder", "p2_sealed")
        proxy_secrets = pumpkin_user_login and name == "p2_anchor_proxy"
        extra_objects = list(durable_objects.values()) if durable_link else []
        if proxy_secrets:
            extra_objects.append(durable_objects["account_store.cpp"])
        if name == "supervisor" and pumpkin_daemon_probe:
            extra_objects.append(compile_source(root / "tests/fixtures/pumpkin/durable_probe_supervisor.cpp",
                                                ("-Os", *durable_flags)))
        if name == "pumpkin_durable":
            extra_objects.extend(compile_source(root / "src/user/pumpkin" / source, ("-Os", *provisioning_flags)) for source in
                                 ("disk_test_store.cpp", "files_slot_client.cpp"))
            if pumpkin_anchored_probe:
                extra_objects.extend(compile_source(root / "src/user/pumpkin" / source, ("-Os", *provisioning_flags)) for source in
                                     ("anchored_files_store.cpp", "snapshot_publication.cpp", "generation_guest.cpp"))
        run([tool("g++"), *X86_FLAGS, "-nostdlib", "-static", "-no-pie",
             "-Wl,--build-id=none,--no-undefined,--fatal-warnings,-z,noexecstack,-z,max-page-size=4096",
             *(["-Wl,--gc-sections"] if name in ("libc_hello", "net_service") or durable_link or proxy_secrets else []),
             "-T", str(sdk / "user.ld"), str(sdk / ("crt0_posix.o" if name in ("runtime_probe", "cpp_runtime_probe", "tls_exit_probe") else "crt0_libc.o" if name in libc_programs else "crt0.o")), main,
             *([str(loader_archive)] if name in ("supervisor", "xos_diag", "files") else []), *fault_objects,
             *([str(core_archive), str(loader_archive)] if name in ("threading_core_probe", "gfxdemo", "terminal") else []),
             *([compile_source(root / "src/user/drivers/uart_16550.cpp")]
               if name in ("terminal", "p2_anchor_proxy") else []),
             *([compile_source(root / "src/user/drivers/virtio_net.cpp")] if name == "net_service" else []),
             *(net_objects if name == "net_service" else []),
                     *([compile_source(root / "src/user/drivers/pc_speaker.cpp")] if name == "audio_tone" else []),
             *([file_ui_object, terminal_control_object, shell_terminal_object] if name == "supervisor" else []),
             *([str(loader_archive)] if name == "supervisor" else []),
                     *([str(loader_archive)] if name == "audio_service" else []),
             *([*interactium_objects] if name in ("interactium", "interactiumd") else []),
             *([*fatfs_objects] if name == "files" else []),
             *(private_broker_objects if name == "files" else []),
             *([compile_source(root / "src/user/pumpkin/account_store.cpp")] if name == "p2_store_probe" else []),
             *extra_objects,
             *([str(loader_archive)] if name == "supervisor" and pumpkin_catalog_fixture else []),
             *(["-Wl,--start-group", str(archive), str(loader_archive), "-L", str(sdk / "lib"),
                "-lc", "-lm", "-lgcc", "-Wl,--end-group"]
               if name in libc_programs else [str(archive)]),
             "-o", str(executable)])
        image = build / f"user_{name}.image.elf"
        strip_all = name == "supervisor" and pumpkin_catalog_fixture
        run([tool("objcopy"), "--strip-all" if strip_all else "--strip-debug", str(executable), str(image)])
        if strip_all:
            def loadable(path):
                raw = path.read_bytes()
                if raw[:7] != b"\x7fELF\x02\x01\x01":
                    raise SystemExit("catalog fixture is not ELF64 little-endian")
                entry, phoff = struct.unpack_from("<QQ", raw, 24)
                stride, count = struct.unpack_from("<HH", raw, 54)
                if stride != 56 or phoff + stride * count > len(raw):
                    raise SystemExit("catalog fixture has invalid program headers")
                loads = []
                for index in range(count):
                    kind, flags, offset, address, physical, size, memory, alignment = struct.unpack_from(
                        "<IIQQQQQQ", raw, phoff + index * stride)
                    if kind == 1:
                        if offset + size > len(raw):
                            raise SystemExit("catalog fixture has invalid load bytes")
                        loads.append((flags, address, physical, size, memory, alignment, raw[offset:offset + size]))
                return entry, loads
            if loadable(executable) != loadable(image):
                raise SystemExit("catalog symbol stripping changed an entry or load segment")
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
        "process_exit_cleanup": {"syscall": 51, "mode": 1, "request_version": 1,
                                 "deadline_max_ns": 30000000000, "guest_qualification": "not_run"},
        "display_extensions": {"version": 1, "syscalls": [65, 66], "pixel_format": "XRGB8888", "surface_count": 1},
        "vm_extensions": {"version": 1, "syscall": 67, "status": "implemented_unqualified"},
        "process_budget": {"version": 1, "syscall": 87, "set_mode": 4, "query_mode": 5,
                           "config_bytes": 64, "snapshot_bytes": 192,
                           "dimensions": ["processes", "pages", "threads", "ipc_objects", "names", "pipes"],
                           "scope": "inherited_cumulative_domains", "guest_qualification": "not_run"},
        "dynamic_controller_observation": {"version": 1, "snapshot_bytes": 72,
                                           "quarantine_reset": "process_lifetime", "automatic_replay": False},
        "thread_extensions": {"join_options": {"version": 1, "syscall": 44, "size": 32,
                                                "third_argument": "options_pointer"},
                              "target_cpu_time": {"version": 1, "syscall": 41, "mode": 1, "size": 56},
                              "guest_qualification": "not_run"},
        "cpu_time": {"version": 1, "syscall": 89, "status": "implemented_unqualified",
                     "unit": "nanoseconds", "scope": ["process", "current_thread", "waited_children"]},
        "ipc_v1": ipc_v1_manifest_entry(),
        "ipc_endpoint": ipc_endpoint_manifest_entry(),
        "observation": observation_manifest_entry(),
        "device_authorization": device_manifest_entry(),
        "network_service": net_configuration,
        "diagnostic_extensions": {"fault_bundle_format": 1, "loader_receipt": "sha256-held-instance",
                                  "diagnostic_shell_command": "diag"},
        "file_identity": {"version": 1, "wire_version": 2, "status": "implemented_unverified",
                          "cwd_operations": [26, 27, 28], "directory_flag": 1024, "pin_flag": 2048,
                          "list_identity_flag": 4096, "list_identity_record_bytes": 13,
                          "positioned_operations": [30, 31], "positioned_preserves_offset": True},
        "process_extensions": {"syscalls": [*range(54, 62), *range(80, 87)], "file_operations": list(range(20, 32)),
            "wait": {"syscall": 20, "nonblocking_flag": 1, "any_flag": 2,
                     "any_target": 0, "completion_bytes": 48, "guest_qualification": "not_run"},
            "thread_pointer": {"syscall": 35, "current_thread_mode": 1, "guest_qualification": "not_run"},
            "startup_versions": [1, 2, 3], "exec_image_abi": 3, "exec_marker": ".xos.exec",
            "fork_supported": True, "exec_supported": True, "single_main_thread_only": True,
            "max_fork_depth": 3, "replacement_reservations": 1, "fd_count": 32, "spawn_argument_bytes": 255,
            "exec_argument_bytes": 4095, "startup_bytes": 16384, "pipe_atomic_bytes": 4096,
            "pipe_wait_write_minimum": True, "pipe_wait_deadline": "implemented_unqualified",
            "stream_lease": {"syscall": 80, "status": "claim_unsupported"},
            "channel": {"syscall": 81, "status": "implemented_unqualified"},
            "ipc_wait": {"syscall": 85, "receive_until_mode": 5, "send_until_mode": 6,
                         "deadline": "absolute_monotonic_ns", "readiness_before_deadline": True,
                         "guest_qualification": "not_run"},
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
    return ([f"user_{name}{suffix}.elf" for name in names for suffix in ("", ".image")] + fixtures +
            (["net_lwip_inputs.json"] if net_configuration["enabled"] else []))
