"""E08-0 audit: measure the host/target toolchain and current XOS limits."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def run(args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def file_type(path):
    try:
        return run(["file", "-b", str(path)])
    except Exception:
        return None


def directory_bytes(path):
    total = 0
    for base, _, names in os.walk(path):
        for name in names:
            try:
                total += (Path(base) / name).stat().st_size
            except OSError:
                pass
    return total


def executable(name):
    path = shutil.which(name)
    return Path(path).resolve() if path else None


def describe(path):
    if path is None:
        return {"present": False}
    return {
        "path": str(path),
        "present": path.is_file(),
        "bytes": path.stat().st_size if path.is_file() else None,
        "type": file_type(path) if path.is_file() else None,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
    }


def main():
    gcc = executable("x86_64-elf-gcc")
    gxx = executable("x86_64-elf-g++")
    if gcc is None or gxx is None:
        raise SystemExit("x86_64-elf-gcc/g++ not found")
    gcc_root = gcc.parent.parent
    binutils = {}
    for name in ("as", "ld", "ar", "ranlib", "strip", "nm", "objcopy"):
        binutils[name] = executable("x86_64-elf-" + name)
    cc1 = Path(run([str(gcc), "-print-prog-name=cc1"])).resolve()
    cc1plus = Path(run([str(gxx), "-print-prog-name=cc1plus"])).resolve()
    libgcc = Path(run([str(gcc), "-print-file-name=libgcc.a"])).resolve()
    libstdcpp_text = run([str(gxx), "-print-file-name=libstdc++.a"])
    libstdcpp = Path(libstdcpp_text).resolve() if libstdcpp_text != "libstdc++.a" else None
    newlib = ROOT / "src/third_party/newlib/x86_64-elf"
    file_abi = (ROOT / "src/shared/include/xos/file_abi.hpp").read_text()
    process_abi = (ROOT / "src/shared/include/xos/process_abi.hpp").read_text()
    work_disk = ROOT / "work_disk.img"
    manifest = json.loads((BUILD / "manifest.json").read_text()) if (BUILD / "manifest.json").is_file() else {}

    otool = shutil.which("otool")
    cc1_deps = []
    if otool:
        for line in run([otool, "-L", str(cc1)]).splitlines()[1:]:
            value = line.strip().split(" (", 1)[0]
            if value:
                cc1_deps.append(value)

    def const(text, name):
        match = re.search(rf"{name}\s*=\s*([0-9* ]+)", text)
        if not match:
            return None
        expr = match.group(1).strip()
        return eval(expr, {"__builtins__": {}}, {}) if re.fullmatch(r"[0-9* ]+", expr) else None

    report = {
        "stage": "E08-0",
        "status": "audit_complete_e08_not_started",
        "versions": {
            "gcc": run([str(gcc), "-dumpfullversion"]),
            "gxx": run([str(gxx), "-dumpfullversion"]),
            "gcc_target": run([str(gcc), "-dumpmachine"]),
            "gcc_configure": next((line for line in run([str(gcc), "-v"]).splitlines()
                                    if line.startswith("Configured with:")), None),
            "binutils_as": run([str(binutils["as"]), "--version"]).splitlines()[0],
            "newlib": "4.6.0.20260123",
            "source_packages": {
                "gcc-16.2.0.tar.xz": {"bytes": 107200820,
                    "url": "https://ftp.gnu.org/gnu/gcc/gcc-16.2.0/gcc-16.2.0.tar.xz"},
                "binutils-2.47.tar.xz": {"bytes": 29034716,
                    "url": "https://ftp.gnu.org/gnu/binutils/binutils-2.47.tar.xz"},
            },
        },
        "host_toolchain": {
            "gcc_driver": describe(gcc),
            "gxx_driver": describe(gxx),
            "gcc_install": {"path": str(gcc_root), "bytes": directory_bytes(gcc_root)},
            "cc1": describe(cc1),
            "cc1plus": describe(cc1plus),
            "libgcc": describe(libgcc),
            "libstdcxx": describe(libstdcpp),
            "cc1_dynamic_dependencies": cc1_deps,
        },
        "binutils": {name: describe(path) for name, path in binutils.items()},
        "newlib": {
            "path": str(newlib),
            "bytes": directory_bytes(newlib),
            "libc": describe(newlib / "lib/libc.a"),
            "libm": describe(newlib / "lib/libm.a"),
        },
        "xos_current_limits": {
            "work_disk_bytes": work_disk.stat().st_size if work_disk.is_file() else None,
            "max_files": const(file_abi, "max_files"),
            "max_file_bytes": const(file_abi, "max_file_bytes"),
            "max_open": const(file_abi, "max_open"),
            "process_max_pages": const(process_abi, "process_max_pages"),
            "process_max_args": const(process_abi, "process_max_args"),
            "tasks": 8,
            "boot_image_limit_bytes": 512 * 1024,
            "kernel_file_bytes": manifest.get("kernel_layout", {}).get("kernel_file_bytes"),
            "kernel_memory_end": manifest.get("kernel_layout", {}).get("kernel_memory_end"),
            "qemu_ram": "64 MiB",
        },
        "findings": [
            "cc1/cc1plus are 38/41 MiB Mach-O arm64 host binaries; they cannot execute on x86_64 XOS.",
            "The complete host x86_64-elf GCC tree is 189 MiB; the current work disk is 16 MiB.",
            "libstdc++.a and libgcc_eh.a are absent; C++ exceptions/RTTI are not buildable yet.",
            "The current file service allows 4 files x 24 KiB and RAM staging; a compiler binary cannot be stored or exec-file'd.",
            "The current child ABI has only console handles 0/1/2; libc open/stat/unlink are ENOSYS; no per-process file session or compiler path I/O.",
            "There is no fork/exec/waitpid/pipe/environment substrate for a compiler driver.",
            "The current process limit is 64 pages (256 KiB); even a stripped cc1 is tens of MiB.",
            "The current 8-task / 64 MiB QEMU baseline is not sized for GCC; changing it needs an explicit memory/disk decision, not a silent bump.",
        ],
        "candidate_decisions_for_e08_1": [
            "Freeze GCC 16.2.0, Binutils 2.47, newlib 4.6.0.20260123 as the seed versions.",
            "Use a dedicated large work disk (candidate >=512 MiB, FAT32) rather than the 16 MiB test disk.",
            "Replace 24 KiB RAM staging with streaming file writes and raise the executable/file limits; do not embed cc1 in the 512 KiB boot image.",
            "Implement per-process file sessions and path I/O before attempting a compiler.",
            "Implement spawn/wait and only the pipe/fork subset actually used by the GCC driver.",
            "Decide the minimum C++ feature set before building libstdc++; do not equate C-only success with G++.",
        ],
        "not_started": True,
    }
    BUILD.mkdir(exist_ok=True)
    (BUILD / "e08_stage0_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({
        "stage": report["stage"],
        "status": report["status"],
        "cc1_bytes": report["host_toolchain"]["cc1"]["bytes"],
        "cc1plus_bytes": report["host_toolchain"]["cc1plus"]["bytes"],
        "gcc_install_bytes": report["host_toolchain"]["gcc_install"]["bytes"],
        "binutils_install_bytes": sum(v.get("bytes") or 0 for v in report["binutils"].values()),
        "libstdcxx_present": report["host_toolchain"]["libstdcxx"]["present"],
        "work_disk_bytes": report["xos_current_limits"]["work_disk_bytes"],
        "max_file_bytes": report["xos_current_limits"]["max_file_bytes"],
        "process_max_pages": report["xos_current_limits"]["process_max_pages"],
    }, indent=2))


if __name__ == "__main__":
    main()
