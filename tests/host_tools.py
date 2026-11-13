# SPDX-License-Identifier: Apache-2.0
"""Platform-selected host tools and flags for tests that build on the CI host.

Cross-compilation to XOS always uses the x86_64-elf GNU toolchain and does not
need these helpers. They exist for host-side unit tests (virtio_net_host,
libc_startup_host, file_identity_host) whose linker/binutils options differ
between Linux, macOS and Windows.
"""
import os
import shutil
import sys

IS_DARWIN = sys.platform == "darwin"
IS_WINDOWS = sys.platform in ("win32", "cygwin", "msys")
IS_LINUX = sys.platform.startswith("linux")


def gc_sections_flags():
    """Linker flags that drop unreachable sections for the host linker."""
    if IS_DARWIN:
        # Apple's ld uses -dead_strip instead of GNU --gc-sections.
        return ["-Wl,-dead_strip"]
    if IS_WINDOWS:
        # Reserved: a MinGW/LLVM host accepts GNU ld flags. A pure MSVC host
        # would need link.exe /OPT:REF and is not wired up here.
        return ["-Wl,--gc-sections"]
    return ["-Wl,--gc-sections"]


def host_compiler(default="c++"):
    """Host C++ compiler command (CXX overrides the default)."""
    return os.environ.get("CXX", default)


def host_cc(default="cc"):
    return os.environ.get("CC", default)


def _program(name):
    executable = name + (".exe" if IS_WINDOWS else "")
    found = shutil.which(executable)
    if found is None:
        raise SystemExit(f"host test requires {executable} on PATH")
    return found


def nm_program():
    # macOS supports Apple nm or llvm-nm; other hosts use GNU-compatible nm.
    # Defined-symbol selection below uses the flag supported by each platform.
    explicit = os.environ.get("NM")
    return explicit if explicit else _program("nm")


def nm_defined_args():
    """Arguments selecting external, defined symbols in portable output."""
    return ["-P", "-g", "-U" if IS_DARWIN else "--defined-only"]


def objcopy_program():
    """GNU objcopy; Apple hosts use llvm-objcopy; Windows reserves llvm-objcopy.exe."""
    explicit = os.environ.get("OBJCOPY")
    if explicit:
        return explicit
    candidates = ["llvm-objcopy", "objcopy"] if IS_DARWIN else ["objcopy", "llvm-objcopy"]
    for name in candidates:
        executable = name + (".exe" if IS_WINDOWS else "")
        found = shutil.which(executable)
        if found is not None:
            return found
    raise SystemExit(
        "host test requires objcopy (GNU binutils or llvm-objcopy) on PATH; "
        "install llvm/binutils or run this test on Linux")
