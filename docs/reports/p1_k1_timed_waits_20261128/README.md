# P1-K1 elapsed waits and explicit interruption

The final source passed six actual guest executions on system
`7ea902f2bff60edf`, using a fresh SDK built from authenticated glibc 2.44
with GCC 16.2.0. Both xsh and the dash rebuilt from that same SDK ran the
interruption fixture, the fork/failed-exec/successful-exec fixture, and the
existing clock-sleep regression. Every run restored the observed baseline
of **129690 free pages, 3 tasks, 1 completion**. The serial transcript is
losslessly compressed in `guest_serial.log.gz`.

The four sleep modes cover relative monotonic `nanosleep`, absolute
monotonic, relative realtime and absolute realtime `clock_nanosleep`. The
fixture observes a real native waiting thread before interrupting it, checks
relative remaining time and absolute remainder preservation, then delivers
the old ticket during a second wait on the same TID and verifies that the
second wait completes normally. Four real concurrent wait slots are exercised
and reclaimed. Static single-thread fork resets ticket state; failed exec
keeps the original runtime usable and successful same-PID exec starts clean.

The production sleep-table host suite passed ten scenario groups normally
and under ASan/UBSan. The production clock conversion suite passed 24 cases
normally and under UBSan. Deterministic fault injection covers duplicate and
expired tickets, malformed/foreign identities, quota exhaustion, spurious
wakes, wait errors after the deadline, and a failed wake after interruption
was already committed. Host tests supplement the actual target observations.

The initial host attempt failed because LeakSanitizer cannot operate under
this host's ptrace restriction. Its report and exact diagnostic are retained;
subsequent runs explicitly disabled leak detection while keeping ASan/UBSan.
LeakSanitizer is not reported as passed. A separate development system/SDK
passed six guest runs before the late-native-error fix; its report and serial
are preserved as historical results and are not the final-source acceptance.

`qualification.json` binds all current system sources and artifacts, all SDK
inputs and artifacts, authenticated source, tools, fixture identities and raw
receipt hashes. `guest.json` records the actual observations. The original
producer manifests still say that the producer did not run guest tests; this
independent qualification supplies the observed result. The flat
`manifest.json` binds every exported leaf. Private operator command paths are
omitted from the public derivative; original local receipts remain intact.

The API is the explicit process-local 48-byte v1 ticket described in
[the contract](../../contracts/libc_timed_waits.md). It reuses syscalls
46/48/49 and has four slots, matching the native thread limit. It provides no
signal delivery or pthread cancellation; `pthread_cancel` stays `ENOTSUP`.
The final guest evidence qualifies static glibc on the recorded QEMU x86-64
system, not shared-libc execution, physical hardware or SMP.
