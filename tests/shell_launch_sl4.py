#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""SL4: one bound system/SDK/tool set, native projects and both shell entrances."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

repo_root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo_root / "scripts"), str(repo_root / "tests")]
from boot_smoke import Guest
from work_disk import transfer
from toolchain import tool
from shell_launch_sl3_make import prepare_project_disk, run_project, export_project, fixture_root
from shell_launch_support import add_arguments, bind_native_inputs, boot_guest, run_case, sha, write_report


def build_probe(sdk, output, report):
    try:
        compiler, c_compiler = tool("g++"), tool("gcc")
    except SystemExit as error:
        raise FileNotFoundError(str(error)) from error
    libgcc = subprocess.check_output([c_compiler, "-print-libgcc-file-name"], text=True).strip()
    command = [compiler, "-std=c++20", "-O2", "-mno-red-zone", "-fno-pie", "-fno-pic",
               "-fno-stack-protector", "-fno-exceptions", "-fno-rtti", "-isystem", str(sdk / "include"),
               "-nostdlib", "-static", "-no-pie", "-Wl,--build-id=none,-z,noexecstack,-z,max-page-size=4096",
               "-T", str(sdk / "user.ld"), str(sdk / "crt0_posix.o"), str(fixture_root / "sl4_runtime.cpp"),
               "-Wl,--start-group", *(str(sdk / "lib" / name) for name in
               ("libxos.a", "libxos_loader.a", "libc.a", "libm.a")), libgcc, "-Wl,--end-group", "-o", str(output)]
    result = subprocess.run(command, capture_output=True, text=True)
    report["probe_build"] = {"command": command, "returncode": result.returncode,
                             "stdout": result.stdout, "stderr": result.stderr}
    result.check_returncode()
    report["probe_build"].update({"elf_sha256": sha(output), "source_sha256": sha(fixture_root / "sl4_runtime.cpp"),
                                  "compiler_sha256": sha(Path(compiler)), "libgcc_sha256": sha(Path(libgcc))})


def install_matrix(disk, folder, bound, report, probe):
    transfer(disk, "import", "/bin/sl4_probe", probe)
    transfer(disk, "import", "/bin/renamed_probe", probe)
    for name in ("sl4_shell.sh", "sl4_nested.sh", "sl4_exec.sh"):
        transfer(disk, "import", "/tests/" + name, fixture_root / name)
        report["fixtures"][name] = sha(fixture_root / name)
    negative = folder / "link_error.sh"
    negative.write_text("#!/usr/bin/dash\n" + bound["tools"]["gcc"]["guest_path"] +
                        " -static --sysroot=/sysroot /src/sl3/link_error.c -o /out/sl3/missing.elf\n")
    transfer(disk, "import", "/tests/link_error.sh", negative)


def run_matrix(guest, bound, report):
    cases = (
        ("ordinary_authority", "sl4_probe query", [b"SL4_QUERY_OK"]),
        ("renamed_same_authority", "renamed_probe query", [b"SL4_QUERY_OK"]),
        ("four_spawn_hops", "sl4_probe chain 4", [b"SL4_CHAIN_LEAF_OK", b"SL4_CHAIN_FOUR_OK"]),
        ("explicit_reduction_and_exec", "sl4_probe reduce", [b"SL4_DENIED_EXEC_OK", b"SL4_REDUCTION_OK"]),
        ("env_cwd_stdio_and_exec_fds", "sl4_probe inherit", [b"SL4_EXEC_FDS_OK", b"SL4_INHERITANCE_OK"]),
        ("legacy_restricted_entry", "exec-file /bin/sl4_probe denied", [b"SL4_DENIED_EXEC_OK"]),
    )
    for name, command, markers in cases:
        run_case(guest, report, name, "xsh", command, markers)
    run_case(guest, report, "authority_inheritance_pipe_nested_shell", "dash", "dash /tests/sl4_shell.sh",
             [b"SL4_QUERY_OK", b"SL4_CHAIN_LEAF_OK", b"SL4_DASH_CHAIN_FOUR_OK", b"SL4_DENIED_EXEC_OK",
              b"SL4_REDUCTION_OK", b"SL4_EXEC_FDS_OK", b"SL4_INHERITANCE_OK", b"SL4_ARGUMENTS_OK",
              b"SL4_PIPE_BYTES_OK", b"SL4_SHELL_CONTEXT_OK", b"SL4_NESTED_DASH_OK", b"SL4_DASH_MATRIX_OK"])
    run_case(guest, report, "explicit_exec_keeps_pid", "dash", "dash /tests/sl4_exec.sh", [b"SL4_DASH_EXEC_PID_OK"])
    line = bound["tools"]["gcc"]["guest_path"] + " -static --sysroot=/sysroot /src/sl3/link_error.c -o /out/sl3/missing.elf"
    for shell, command in (("xsh", line), ("dash", "dash /tests/link_error.sh")):
        output = run_case(guest, report, "real_link_failure", shell, command, expected=None)
        if b"undefined reference" not in output:
            report["checks"][-1]["status"] = "failed"
            raise AssertionError("nonzero command did not reach the expected GNU linker failure")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument("--report", type=Path, default=repo_root / "build/shell_launch_sl4/report.json")
    args = parser.parse_args()
    report = {"gate": "SL4", "status": "not_run", "guest_execution": "not_run", "checks": [],
              "planned_command_groups": 14,
              "not_applicable": {"xsh_shell_syntax": "no shell cd/export, quoting, pipes, subshell or replacing exec; application API inheritance is tested",
                                 "spawn_fd_above_2": "current startup-v2 spawn contract transfers stdio; 32-FD/CLOEXEC is checked through fork+exec"},
              "limits": {"xsh_chain": "four application spawn hops", "dash_chain": "dash plus three application hops; no increase to the existing process budget"}}
    guest = None
    code = 1
    try:
        bound = bind_native_inputs(args, report)
        if args.preflight_only:
            report["status"] = "preflight_passed"
            code = 0
        else:
            with tempfile.TemporaryDirectory(prefix="xos_sl4_native_") as temporary:
                folder = Path(temporary)
                probe = folder / "sl4_probe"
                build_probe(args.system / "sdk", probe, report)
                disk = prepare_project_disk(args, bound, folder, report)
                install_matrix(disk, folder, bound, report, probe)
                guest = Guest(args.system / "xos-install.iso", "sl4_native", work_disk=disk, iso=True)
                report["qemu_command"] = guest.command
                report["guest_execution"] = "started"
                boot_guest(guest)
                run_project(guest, report)
                run_matrix(guest, bound, report)
                guest.close()
                args.report.parent.mkdir(parents=True, exist_ok=True)
                (args.report.parent / "serial.log").write_bytes(guest.output)
                guest = None
                export_project(disk, folder, report)
                report["status"] = report["guest_execution"] = "passed"
                code = 0
    except FileNotFoundError as error:
        report["status"] = "not_run" if report["guest_execution"] == "not_run" else "failed"
        report["error"] = str(error)
        code = 2 if report["status"] == "not_run" else 1
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    finally:
        if guest is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            (args.report.parent / "serial.log").write_bytes(guest.output)
            guest.close()
        write_report(args.report, report)
    print(report["status"].upper(), "SL4:", len(report["checks"]), "guest command groups")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
