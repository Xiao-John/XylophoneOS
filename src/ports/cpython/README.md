# CPython for XOS

This directory ports CPython 3.14.9 to XOS following
`docs/cpython_port_plan.md`. PY0a (cross configure + static link), PY0b
(`-c`, scripts, Unicode, exceptions, GC, import, repeated start), PY1
(reproducible install stage, script path rules, selected standard library and
failure exits), T3-PY (real pthreads with the GIL), and PY2 (basic REPL,
`input()`, files and reboot-persistent JSON) have passed their guest gates. The
interpreter is a static ELF with the GIL; PY3 A1 selected-library checks, A2
zlib 1.3.2 and A3's locked offline pure-Python wheel path also pass. It is not
a POSIX platform.

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

/usr/bin/python3 scripts/build_cpython.py \
  --sdk build/threading_sdk \
  --archive .cache/xos_seed/cpython/sources/Python-3.14.9.tar.xz \
  --build-python .cache/xos_seed/cpython/host_build/python.exe \
  --compile-probe
/usr/bin/python3 scripts/stage_cpython.py \
  --work .cache/xos_seed/cpython/<fingerprint>
/usr/bin/python3 tests/cpython_py2_smoke.py \
  --work .cache/xos_seed/cpython/<fingerprint>

/usr/bin/python3 scripts/build_cpython_zlib.py --sdk build/threading_sdk
/usr/bin/python3 scripts/build_cpython.py \
  --sdk build/threading_sdk \
  --archive .cache/xos_seed/cpython/sources/Python-3.14.9.tar.xz \
  --build-python .cache/xos_seed/cpython/host_build/python.exe \
  --zlib-prefix .cache/xos_seed/cpython/zlib/<fingerprint>/prefix \
  --compile-probe
/usr/bin/python3 scripts/stage_cpython.py \
  --work .cache/xos_seed/cpython/<fingerprint> --phase PY3
/usr/bin/python3 tests/cpython_py3_a2_smoke.py \
  --work .cache/xos_seed/cpython/<fingerprint>
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

The PY2 patch selects CPython's basic REPL on XOS and supplies a small console
line reader shared by the REPL and `input()`. It waits across empty UART reads,
accepts CR or LF, echoes input, erases the last UTF-8 code point on Backspace or
DEL, and treats Ctrl-D on an empty line as EOF. The guest gate uses a fresh 2
GiB temporary disk and verifies interactive use, file and directory behavior,
short reads, expected failures, UTF-8 JSON save, `sync`, reboot and reload.
Escape is still a supervisor force-cancel, not Python `KeyboardInterrupt`.
Evidence is written to `build/cpython_py2_report.json`.

PY3 A1 uses the already accepted no-zlib interpreter to verify SHA-2/SHA-3/
BLAKE2/MD5/SHA1 and HMAC known vectors, plus selected operations from pathlib,
argparse, dataclasses, tomllib, decimal, XML and stored zipfile. `statistics`
currently fails during its `random` dependency's default seed because XOS has no
system entropy; this remains an explicit blocker. Evidence is written to
`build/cpython_py3_a1_report.json`.

For A2, `build_cpython_zlib.py` verifies the official zlib 1.3.2 source archive,
applies the small XOS `errno.h` portability patch and builds a static `libz.a`
under an input fingerprint. Pass its `prefix/` to `build_cpython.py` with
`--zlib-prefix`; the option is bound into the CPython fingerprint and enables
the built-in `zlib` module. `stage_cpython.py --phase PY3` adds the Zlib license
to the install manifest and stage. The guest gate tests streaming compression,
gzip, deflate ZIP, zipimport, and malformed/truncated data. Evidence is written
to `build/cpython_py3_a2_report.json`.

For A3, `src/ports/cpython/idna_lock.json` pins the official idna 3.20
`py3-none-any` wheel and license. `scripts/xypm_python_wheel.py` checks the
wheel hash, pure tag, member paths/types, `RECORD` hashes and sizes, and
preserved license before creating an ordinary XPK package for the frozen B2
profile. It installs package files only under `/usr/lib/python3.14/site-packages`
and carries the license and build receipt. `tests/cpython_py3_a3_smoke.py`
verifies guest import/IDNA behavior, xypm candidate-image install/remove,
source-image preservation, wrong-hash rejection and native-module rejection.
This first slice does not resolve dependencies or generate console scripts and
does not support online pip, venv, source builds or native wheels. Evidence is
written to `build/cpython_py3_a3_report.json`.

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
- Real pthread-backed Python threads have passed T3-PY with the GIL. There is
  still no fork/exec, select, symlink/link, chroot, fsync, pty, dynamic `.so`
  loading or sockets. `subprocess`, `resource`, `select`, `fcntl`, `mmap`,
  `termios` and related modules are not built. XOS pipes remain nonblocking.
- The user stack is 128 KiB. This build needs `-O2`; unoptimized CPython
  overflows the stack during import.
- The basic REPL is intentionally minimal: no readline/history/full terminal
  editing and no Ctrl-C/`KeyboardInterrupt`. CR and LF were tested separately;
  Escape terminates the whole foreground process through the supervisor.
- `-c` needs `linecache.py` in this CPython version even for a one-line command.
- `statistics` is not currently usable because importing it seeds `random` from
  system entropy; no deterministic or insecure fallback is installed.

## Layout

```text
source_lock.json          frozen archive/sigstore/spdx hashes
patches/0001…0003         platform, modules, pthread and thread-state glue
patches/0004…             basic REPL and console line input
zlib_lock.json             pinned zlib archive and license hashes
zlib_patches/              XOS errno header portability patch
config/xos_config.site    explicit autoconf overrides
xos_time.cpp              XOS timing/sleep bridge objects
```

CPython keeps its PSF and bundled third-party licenses; the pinned archive's
`LICENSE` is not copied into this directory. New XOS build/test files are
Apache-2.0, and modified upstream files retain their original notices. No
upstream archive is committed here.
