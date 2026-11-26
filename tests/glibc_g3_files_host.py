#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test production glibc FD/session logic with only the kernel trap substituted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    "basic", "bounds", "access_legacy_stat", "spawn_cwd_serialization", "concurrent",
    "public_lease", "native_read_capacity",
    "block_valid", "block_bad_value", "block_bad_payload", "block_zero_success", "block_large_success",
    "anonymous_valid", "anonymous_bad_handle", "anonymous_bad_inode", "anonymous_bad_flags",
    "anonymous_bad_size", "anonymous_bad_payload",
    "directory_legacy", "directory_identity",
    "directory_bad_cursor", "directory_bad_identity", "directory_bad_utf8",
    "directory_bad_count", "directory_truncated", "directory_default_limit", "directory_empty_progress",
    "inheritance", "inheritance_word_aligned", "invalid_inheritance",
    "duplicate_cleanup", "pipe_lease", "pipe_writev", "no_session", "wrong_sequence", "bad_magic",
    "inheritance_v2", "duplicate_v2_handle", "path_v2_redirection",
    "bad_version", "overread", "overwrite", "unknown_status", "metadata", "timeout",
    "service_death", "clock_failure", "late_reply", "send_failure", "short_reply",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/glibc_g3_files_host")
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    overlay = ROOT / "src/ports/glibc/sysdeps/xos"
    terminal_sources = [str(ROOT / 'src/ports/glibc/terminal_support.cpp'),
                        str(ROOT / 'src/user/sdk/terminal_client.cpp')]
    sources = [ROOT / "src/user/services/files.cpp", ROOT / "src/user/loader/elf.cpp",
               ROOT / "src/third_party/fatfs/ff.c",
               ROOT / "src/shared/include/xos/file_abi.hpp", Path(__file__).resolve()]
    sources += list(overlay.glob("xos_file*"))
    sources += [overlay / "writev.c", overlay / "bits/stat.h", overlay / "bits/fcntl.h",
                ROOT / "tests/fixtures/glibc_g3/host_aliases.h",
                ROOT / "tests/fixtures/file_semantics/libc_service.cpp",
                ROOT / "tests/fixtures/file_semantics/file_semantics.cpp",
                ROOT / "src/user/services/fatfs_unicode.cpp",
                ROOT / "src/third_party/fatfs/ff.h"]
    sources += list((ROOT / "tests/fixtures/glibc_g3").glob("*.cpp"))
    sources += [ROOT / "src/user/sdk/file_client.cpp"]
    sources += list((ROOT / "src/user/include/xos").rglob("*.hpp"))
    sources += list((ROOT / "src/shared/include/xos").rglob("*.hpp"))
    sources += list(map(Path, terminal_sources)) + list(overlay.glob('xos_terminal*'))
    source_inputs = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sorted(set(sources))}
    flags = ["-D_GNU_SOURCE", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
             "-Wconversion", "-Wshadow", "-I", str(overlay)]
    if args.sanitize:
        flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                  "-fno-omit-frame-pointer"]
    cc, cxx = os.environ.get("CC", "gcc"), os.environ.get("CXX", "g++")
    exe = output / "runtime_test"
    runtime_objects = []
    for name in ("xos_file_runtime", "xos_file_session"):
        obj = output / (name + ".o")
        subprocess.run([cc, "-std=c11", "-DXOS_GLIBC_FILE_TEST", *flags, "-c",
                        str(overlay / (name + ".c")), "-o", str(obj)], check=True)
        runtime_objects.append(str(obj))
    writev = output / "writev.o"
    subprocess.run([cc, "-std=c11", *flags, "-include",
                    str(ROOT / "tests/fixtures/glibc_g3/host_aliases.h"), "-c",
                    str(overlay / "writev.c"), "-o", str(writev)], check=True)
    subprocess.run([cxx, "-std=c++17", *flags, "-I", str(ROOT / "src/shared/include"),
                    "-I", str(ROOT / "src/user/include"),
                    str(ROOT / "tests/fixtures/glibc_g3/files_runtime.cpp"), *runtime_objects, str(writev),
                    str(ROOT / "src/user/sdk/file_client.cpp"),
                    *terminal_sources,
                    "-pthread", "-o", str(exe)], check=True)
    results = []
    environment = os.environ.copy()
    if args.sanitize:
        environment["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=1"
        environment["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    for case in CASES:
        run = subprocess.run([str(exe), case], text=True, capture_output=True,
                             env=environment, timeout=30)
        (output / f"{case}.log").write_text(run.stdout + run.stderr)
        results.append({"case": case, "status": "pass" if run.returncode == 0 else "fail",
                        "returncode": run.returncode})
        (output / "report.json").write_text(json.dumps({
            "scope": "production FD/session state machine; simulated kernel and files service",
            "sanitizers": ["address", "undefined"] if args.sanitize else [],
            "leak_sanitizer": "not_run" if args.sanitize else "not_requested",
            "guest": "not_run", "results": results, "sources": source_inputs,
            "status": "running" if run.returncode == 0 else "failed",
        }, indent=2) + "\n")
        if run.returncode != 0:
            raise SystemExit(f"FAIL {case}\n{run.stdout}{run.stderr}")
        print(run.stdout.strip())
    print(f"PASS {len(results)} glibc G3-F host cases")
    # Run the real files service and FatFs in a separate TU with host headers;
    # only the IPC trap/session identity boundary is replaced.
    service_flags = ["-std=c++20", "-O1", "-g", "-ffunction-sections", "-fdata-sections",
                     "-I", str(ROOT / "src/user/include"), "-I", str(ROOT / "src/shared/include"),
                     "-I", str(ROOT / "src/third_party/fatfs")]
    if args.sanitize:
        service_flags += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                          "-fno-omit-frame-pointer"]
    service_objects = []
    for filename, source in [
        ("fatfs.o", "src/third_party/fatfs/ff.c"),
        ("unicode.o", "src/user/services/fatfs_unicode.cpp"),
        ("elf.o", "src/user/loader/elf.cpp"),
        ("service.o", "tests/fixtures/file_semantics/libc_service.cpp"),
    ]:
        target = output / filename
        subprocess.run([cxx, *service_flags, "-w", "-c", str(ROOT / source), "-o", str(target)], check=True)
        service_objects.append(str(target))
    service_exe = output / "service_test"
    subprocess.run([cxx, "-std=c++20", *flags, "-I", str(ROOT / "src/shared/include"),
                    "-I", str(ROOT / "src/user/include"),
                    str(ROOT / "tests/fixtures/glibc_g3/files_service.cpp"), *runtime_objects,
                    *terminal_sources,
                    *service_objects, "-Wl,--gc-sections", "-o", str(service_exe)], check=True)
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_work_disk import make_image
    private_image = output / "private_test.img"
    private_image.write_bytes(make_image())
    run = subprocess.run([str(service_exe), str(private_image)], text=True, capture_output=True,
                         env=environment, timeout=60)
    (output / "real_service.log").write_text(run.stdout + run.stderr)
    private_image.unlink()
    print(run.stdout.strip())
    if run.returncode != 0:
        raise SystemExit(f"FAIL real files/FatFs integration\n{run.stdout}{run.stderr}")
    report = json.loads((output / "report.json").read_text())
    report["real_files_fatfs"] = {"status": "pass", "groups": 15,
                                 "kernel_transport": "simulated"}
    after = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(set(sources))}
    report["inputs_unchanged"] = after == source_inputs
    report["status"] = "passed" if report["inputs_unchanged"] else "failed"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    if not report["inputs_unchanged"]:
        raise SystemExit("source inputs changed during test")


if __name__ == "__main__":
    main()
