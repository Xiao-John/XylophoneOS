# CPython for XOS

This directory ports CPython 3.14.9 to XOS following
`docs/cpython_port_plan.md`. PY0a (cross configure + static link), PY0b
(`-c`, scripts, Unicode, exceptions, GC, import, repeated start), and PY1
(reproducible install stage, script path rules, selected standard library and
failure exits) pass against the frozen 0.0.1-1024 SDK. The interpreter is a
static ELF with the GIL and CPython's single-thread pthread stubs; it is not a
POSIX platform.

## Build and test

```sh
/usr/bin/python3 scripts/build_cpython.py \
  --sdk build/releases/0.0.1-1024/sdk \
  --archive .cache/xos_seed/cpython/sources/Python-3.14.9.tar.xz \
  --build-python .cache/xos_seed/cpython/host_build/python.exe \
  --compile-probe

/usr/bin/python3 tests/cpython_py0b_smoke.py

/usr/bin/python3 scripts/stage_cpython.py
/usr/bin/python3 tests/cpython_py1_smoke.py
```

The build script verifies the archive hash, hashes the port tree and SDK into a
fingerprint, patches a private source copy, builds a matching host Python when
no `--build-python` is supplied, and writes everything under
`.cache/xos_seed/cpython/<fingerprint>/`. It never installs into an XOS disk and
never invokes the shared build or QEMU. The result is
`target_build/python.exe` plus `py0a_report.json`.

The guest test copies a stripped interpreter and the Python standard library
(minus `test/`, `idlelib/`, `tkinter/`, `turtledemo/`, `ensurepip/`,
`lib2to3/`) into a temporary FAT32 disk under `/usr/bin/python3` and
`/usr/lib/python3.14/`, boots `build/xos.img`, and writes
`build/cpython_py0b_report.json`.

The PY1 staging script accepts only the fingerprint named by the passed PY0b
report. It creates a fixed 560-file tree under `stage_py1/` and records every
installed path, size and SHA256 in `stage_py1_manifest.json`; an existing
partial stage is never overwritten. The PY1 guest test copies that tree and
its fixtures to a fresh temporary disk. It verifies exact `argv`, cwd `/`, the
inherited `PATH`, script-directory-first import with no host path leakage,
binary file bytes, useful operations from `json`, `re`, `collections`,
`itertools`, `functools` and `math`, and exit 1 for a missing module, syntax
error and unhandled exception. Evidence is written to
`build/cpython_py1_report.json`.

## Configuration

- Target `x86_64-unknown-xos`, prefix `/usr`, static modules only
  (`MODULE_BUILDTYPE=static`), no mimalloc, no readline, no IPv6.
- `config/xos_config.site` overrides autoconf results that are false positives
  on XOS: chroot/link/symlink/fchdir/fsync/fdatasync/setgroups/fork, sched.h,
  `sys/resource.h`, posix_spawn, mmap and pty probes.
- `Modules/Setup.stdlib.in`-driven modules that need fork/exec, select, pty,
  dlopen or zoneinfo are marked n/a for XOS in `configure`.
- `xos_time.cpp` provides the monotonic clock in 10 ms PIT ticks, a `times()`
  wrapper that reports ENOSYS to newlib's `clock()`, and a spin-based
  `time.sleep()`.

## Honest limits of this profile

- The hash seed is deterministic (`0`). This is an explicit bootstrap profile,
  not secure randomness; `os.urandom`/`secrets` are not provided.
- `time.sleep()` spins on PIT ticks and consumes CPU. There is no blocking
  timer or wakeup service.
- There is no wall clock: `gettimeofday` is ENOSYS, so `time.time()` and
  `datetime.now()` are unavailable. `timezone`/`daylight` stay at newlib's
  zero defaults because XOS has no zoneinfo database.
- `time.process_time()` raises `RuntimeError` because XOS has no CPU-time
  accounting.
- No fork/exec, select, symlink/link, chroot, fsync, pty, dynamic `.so`
  loading, sockets or threads. `subprocess`, `resource`, `select`, `fcntl`,
  `mmap`, `termios` and related modules are not built.
- The user stack is 128 KiB. This build needs `-O2`; unoptimized CPython
  overflows the stack during import.
- The traditional REPL has not been validated. `-c` needs `linecache.py` in
  this CPython version even for a one-line command.

## Layout

```text
source_lock.json          frozen archive/sigstore/spdx hashes
patches/0001…             XOS platform admission, time and tz glue
patches/0002…             module scope, static link group, tick/seed glue
config/xos_config.site    explicit autoconf overrides
xos_time.cpp              XOS timing/sleep bridge objects
```

CPython keeps its PSF and bundled third-party licenses; the pinned archive's
`LICENSE` is not copied into this directory. New XOS build/test files are
Apache-2.0, and modified upstream files retain their original notices. No
upstream archive is committed here.
