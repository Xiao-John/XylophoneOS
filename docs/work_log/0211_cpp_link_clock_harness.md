# 0211 — C++ link investigation, guest clock `_times`, and serial-driver flush

## Scope

Follow-up to the 0.0.2-1103 blind test: explain the reported 11-minute C++
link, fix the guest clock used by `clock()/times()`, fix the serial test
driver's partial-line logging, and record the remaining findings as debt.
No `main` commit.

## C++ link finding

The 11-minute figure was not linker time.  With `trace on`, the same integrated
C/C++ build completed in 55.0 s (`pid=45` exited code=0); a C++ string link took
8.0 s.  `xsh> ` has no newline and the old pipe driver logged only complete
lines, so a completed build looked like a hang.  See
`build/cpp_link_investigation/report.md`.

## Changes

- `src/user/libc/newlib_syscalls.cpp`
  - `_times()` now returns monotonic ticks at newlib's x86_64 `CLOCKS_PER_SEC`
    (1000 Hz) instead of `ENOSYS`/`(clock_t)-1`; `tms_utime` is set and the other
    fields are zero.
  - added `times()` as the `_times()` forwarding entry point needed by the
    newlib reentrant `clock()` path.
  - limitation recorded: this is wall time from the first clock/times call; XOS
    has no per-process CPU accounting ABI.
- `blind_test/tools/pipe_drive.py`
  - idle-flushes a partial output buffer after 250 ms, so `xsh> ` prompts and
    other no-newline output are timestamped instead of waiting for the next
    newline.  Final flush retained.

## Evidence

- Driver probe: `printf 'xsh> '; sleep 1; printf 'done\n'` logs the prompt at
  0.50 s and `done` at 1.0 s.
- Guest clock probe built against a temporary `libxos.a` with the new object and
  imported into a release work-disk copy:
  `clock_first=0 clock_second=20 delta=20 work=...`, exit 0.
- `newlib_syscalls.cpp` compiles with the toolchain flags to
  `build/cpp_link_investigation/newlib_syscalls_clock.o`.

## Not run

- Full XOS/compiler rebuild; the shipped `x86_64-elf-g++` binary still contains
  the old `_times`, so its `-ftime-report` remains wrong until the compiler/SDK
  is rebuilt and republished.
- Full release smoke.
- The remaining blind-test items are recorded in `docs/tech_debt.md` §6.

## Next

Rebuild the guest compiler/SDK from this source, rerun `-ftime-report`, and
close BT-08; address BT-01..BT-07 by their listed exit conditions.
