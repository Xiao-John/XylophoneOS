"""One pinned compiler configuration, split into common and ISA-specific flags."""
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "config/toolchain.json").read_text())
TARGET = json.loads((ROOT / "config/x86_64_bios.json").read_text())
COMMON_FLAGS = [
    "-std=c++20", "-ffreestanding", "-nostdinc++", "-fno-exceptions", "-fno-rtti",
    "-fno-stack-protector", "-fno-threadsafe-statics", "-fno-use-cxa-atexit",
    "-fno-unwind-tables", "-fno-asynchronous-unwind-tables", "-fno-omit-frame-pointer",
    "-fno-pic", "-fno-pie", "-g3", "-gdwarf-4", "-O2", "-Wall", "-Wextra",
    "-Werror", "-Wconversion", "-Wshadow",
]
X86_FLAGS = ["-m64", "-march=x86-64", "-mtune=generic", "-mcmodel=small",
             "-mno-red-zone", "-mgeneral-regs-only"]


def tool(name):
    prefix = os.environ.get("CROSS_PREFIX", "x86_64-elf-")
    path = shutil.which(prefix + name)
    if path is None:
        raise SystemExit(f"Missing {prefix + name}; see docs/toolchain.md")
    return path


def output(command):
    return subprocess.check_output(command, text=True).strip()


def audit():
    compiler = tool("g++")
    gcc = tool("gcc")
    ld = tool("ld")
    versions = {
        "gcc": output([gcc, "-dumpfullversion"]),
        "g++": output([compiler, "-dumpfullversion"]),
        "target": output([compiler, "-dumpmachine"]),
        "ld": output([ld, "--version"]).splitlines()[0],
        "nasm": output([os.environ.get("NASM", "nasm"), "-v"]),
    }
    if versions["gcc"] != LOCK["gcc"] or versions["g++"] != LOCK["gcc"]:
        raise SystemExit(f"GCC version mismatch: {versions}; expected {LOCK['gcc']}")
    if versions["target"] != LOCK["target"] or not versions["ld"].endswith(LOCK["binutils"]):
        raise SystemExit(f"Cross target/Binutils mismatch: {versions}")
    if not versions["nasm"].startswith("NASM version " + LOCK["nasm"] + " "):
        raise SystemExit("NASM version differs from config/toolchain.json")
    executables = {name: tool(name) for name in ("gcc", "g++", "as", "ld", "objcopy", "nm", "ar")}
    for name in ("cc1", "cc1plus"):
        executables[name] = output([compiler, "-print-prog-name=" + name])
    for name in ("as", "ld"):
        configured = output([compiler, "-print-prog-name=" + name])
        resolved = shutil.which(configured)
        if resolved is None or Path(resolved).resolve() != Path(executables[name]).resolve():
            raise SystemExit(f"Compiler's configured {name} differs from selected cross tools")
    executables["nasm"] = shutil.which(os.environ.get("NASM", "nasm"))
    versions["executables"] = {
        name: {"path": str(Path(path).resolve()),
               "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        for name, path in executables.items()
    }
    return versions
