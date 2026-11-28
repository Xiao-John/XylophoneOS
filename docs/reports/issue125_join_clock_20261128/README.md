# Issue #125: bounded join and target-thread CPU clock qualification

These are minimal derived receipts from actual builds and QEMU runs in the
published `xos-sdk-glibc-preview-3` development environment. The base was
`344655c3f2279a10c62fce5ea039c741aa6172f1`; the changed source bytes are bound by
`inputs.json` and this report's Git commit. Released SDK assets were not altered.
Exported serial logs normalize line endings and remove trailing whitespace;
message text and events are retained. Raw originals remain identified by their
recorded hashes.

## Results

- Default glibc: three complete public-API runs, including a real fork child's
  refusal to query its parent's thread clock, before entering the threaded profile.
- Rebuilt threaded newlib: three complete public-API runs using its original
  unsigned-long `clockid_t`. Its existing lack of threaded fork is preserved.
- New glibc on the old main kernel: one run confirms immediate extension
  rejection without changing outputs or silently blocking, followed by successful
  legacy join. `sys89` v1 remains unchanged.
- Actual new-kernel runs cover live `EBUSY`, expired and bounded joins,
  invalid requests, join/detach contention, timeout releasing ownership, results
  consumed once, busy versus blocked target CPU counts, resolution, dead-but-not-yet-
  joined clocks, detached lifetime, eight rounds of slot reuse and resource recovery.
- The existing glibc thread suite passes all four cases: synchronization/TLS,
  initial-thread exit, 16 rounds of detach/cleanup, and bounded blocked-stdio exit.
- The freestanding G1 bridge passes four rounds. Its linked objects are verified
  byte-for-byte against members of the completed SDK's `libc.a`; identity,
  scheduling rejection, target CPU clock, names and signal-zero behavior are retained.

The new system is `ebaea6ff03805bad`; each application run restores the measured
resource baseline of `129692 / 3 / 1`. The old kernel has its own baseline,
`129693 / 3 / 1`. The raw reports' hashes identify the local originals; path-heavy
commands are presented as reproducible relative commands in the work log rather
than republished as machine-specific paths.

The actual glibc and legacy timedjoin wrappers also pass deterministic UBSan
checks for preemption between clock samples, an early native timeout followed by
retry, a final expired atomic join, and immediate rejection on the old kernel.
Independent review first reproduced a wall-first sampling bug; the fix samples
monotonic time first and retries against the original absolute wall deadline.
Both SDKs and the system snapshot were rebuilt, and all guest matrices recorded here
were rerun on those final bytes. Earlier diagnostic passes are not reused.

## Boundaries

No new syscall number, cross-process CPU authority, asynchronous cancellation,
CPU timer, SMP or shared-library runtime qualification is claimed. The new CPU
query is restricted to a live thread in the calling process. Private clock IDs
cannot revive after exit or slot reuse. The old ordinary single-thread pthread
profile remains deliberately restricted. Hardware timing calibration was exercised
only on the recorded QEMU TCG configuration.

The first diagnostic fixture used `nanosleep`, which is absent from this glibc
baseline; its scheduling helper now uses the existing native absolute wait.
A second diagnostic placed `fork` after entering the threaded profile and was
correctly rejected. The final fixture tests fork isolation before creating threads.
These failures were not counted as passes and did not require relaxing runtime checks.

The G1 full-SDK link needs the identity, scheduling and names/signal object groups.
Its original default Unix QMP socket was denied in this SDK environment; the final
run uses the existing QMP pipe transport. The main issue runner is serial-only.

The flat `manifest.json` binds every leaf in this directory. Full reproducible
commands and the actual unsupported boundaries are in the
[work log](../../work_log/fddca1b7_issue_125_bounded_joins_and_target_thread_cpu_cl.md).
