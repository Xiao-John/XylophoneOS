# Public runtime capsule and thread-arena collision

This is a preserved **failed** ordinary public-runtime attempt, not a P0
qualification. The exact system `e8b8ba5e2645c5c2`, public GNU v3 and shared
GCC v2 passed six recorded cases: C startup, runtime loading policy denial,
ordinary `posix_spawn`, same-PID `execve`, and shared C++ exception/RTTI/unwind
entry through both xsh and dash. Each restored its initial resource baseline
of 129680 free pages, 3 processes and 1 completion record.

The seventh case, `thread-xsh`, failed when the real shared `std::thread`
constructor received `ENOTSUP` from `pthread_create`. The eighth case,
`thread-dash`, did not run. The report retains the failure, real kernel
process completion and serial trace; it has not been relabeled as passing.

The source review located the concrete collision: internal startup capsule
version 1 placed readonly pages at `0x70000000`, exactly the beginning of the
kernel worker stack/TLS arena `[0x70000000, 0x71000000)`. The kernel's explicit
thread-profile opt-in correctly rejects any existing mapping in that range.
Commit `7bbe6a73` moves the capsule to `0x71000000`, increments its internal
version, binds the actual ABI headers into the native identity, and checks
all reserved regions. It also rejects an approved bootstrap whose actual
LOADs overlap the capsule or worker arena. These are separate new source
bytes; this failed report is not evidence that the correction executed.

`failed_guest.json` retains every original input/source/tool/SDK digest and
all seven recorded outcomes. All bound inputs were checked again before
this export. `conversion.json` identifies the original report and serial
bytes. Only explicit environment roots were mechanically converted to
replay templates. The flat manifest covers every exported leaf. New native
SDK, GNU runtime, C++ DSOs and application roots must be qualified in a
separate report before the public worker path is considered complete.

Guest command templates `XOS_GUEST_TESTS` and `XOS_GUEST_APPS` represent
`/tests` and `/apps`. They are applied only to the seven shell command fields;
host source paths, artifact identities and raw serial bytes are unchanged.
