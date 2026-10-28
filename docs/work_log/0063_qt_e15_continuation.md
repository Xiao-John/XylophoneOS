# 0063 QtCore XOS continuation — candidate evidence, not qualification

Branch `codex/qt6-e15`, baseline upstream `244ac40`; continuing PR #8.
No new ABI allocation. This work uses QtBase 6.8.3 source lock and separate
threading SDK. Files in `src/ports/qt6` contain the replayable source patches,
XOS event dispatcher, mutex backend and exact target feature configuration.
`prepare_source.py` verifies the original archive and refuses overwriting trees.
`configure_target.py` disables poll/select, dynamic libraries, network,
process APIs and the known false-positive probes; `build_fixture.py` uses
matching host tools and emits a provenance receipt.

The restricted dispatcher owns a coalescing wait word. Its single consumer clears
it before inspecting posted events; producer stores a pending bit then wakes,
and kernel `wait_word` atomically checks the bit before blocking. A bit rather
than a wrapping generation counter avoids 2^32 wake ABA. Qt's timer list uses
steady-clock deadlines; a failed wait/wake terminates visibly. Nested loops use
Qt's existing timer-list reentrancy handling. Socket/FD notifiers are rejected
and disabled; no multi-source poll is claimed. Dispatcher destruction requires
Qt's normal thread ownership/lifetime protocol; fault cleanup is a kernel test,
not proof of arbitrary concurrent destruction safety.

QMutex's slow path uses the real pthread mutex and monotonic condition variable;
Qt thread cancellation is unsupported, warns/fails, and normal QThread exit
calls `finish()`. Direct external pthread exit through a Qt worker is unqualified.
QFile memory mapping returns ENOTSUP and Qt resource/translator paths use their
buffered fallbacks. Canonical path, ownership, chmod, links, no-replace rename,
XDG runtime ownership and dynamic library operations are unsupported; no
successful POSIX stubs or new kernel ABI were added. QtCore's explicitly
failing compatibility shims return ENOTSUP, not successful results. Qt's
QStorageInfo unavailable platform implementation reports no storage information.

## Preliminary real executions

All evidence in `../reports/qt_e15_continuation_20261028/` is **candidate**;
these runs used an uncommitted source tree and previous system image/SDK, and
must not be interpreted as final commit-bound G01/G03. The Qt 6.8.3 target
Core archive and linked static Qt ELF were actually built. Tests used QEMU 11.1.2,
TCG, i440fx, one `qemu64,+rdrand` CPU, 512 MiB, private FAT32 disk. Their
JSON records exact image/ELF hashes, commands and resource counters; raw serial
bytes are compressed without text conversion.

- PASSED: wait-word wake-before-wait, timed wait, worker wake, observed waiting,
  wake/timeout race and destruction after join (small bounded sample).
- PASSED: Qt posted events, nested loop, timer deadline, interrupt, observed
  kernel waiting and QThread join; QString/QByteArray, real resource, QFile/QDir,
  EOF/missing file, timer cancellation, QMutex and QWaitCondition timeout.
- PASSED: Qt worker quota: three workers joined, fourth rejected, no residual
  resources; fault with a worker alive produced vector 6 and reclaimed baseline.
- PASSED: Qt file write and sync, reboot then second Qt process reads same bytes;
  FAT read-only attribute and synthetic full-FAT error each returned failure,
  and offline post-close inspection confirmed original contents preserved.
- FAILED: target link before explicit unsupported XOS adaptation, including
  missing UID, permission, symlink and POSIX file functions. Logs are retained;
  unsupported results are not represented as successes.

These runs do not validate all scheduling interleavings, memory exhaustion,
performance/peak memory, dynamic plugins or file-name Unicode. They are not a
license or distribution qualification. G01/G03 and final source-bound regressions
remain NOT_RUN until a clean-source build, complete gate tests and matching
system/SDK artifacts are recorded.

Subsequent whole-archive symbol inventory found unreferenced `getuid`, `*at`
and `sigaction` dependencies despite successful section-garbage-collected app
linking. The XOS patch now selects Qt's explicit unsupported trash path and
avoids SIGPIPE setup because XOS pipes return EPIPE and do not deliver SIGPIPE.
After recompilation, comparison of QtCore undefined symbols against the actual
Qt/SDK static archives leaves only the linker-provided `_GLOBAL_OFFSET_TABLE_`;
this is a static symbol inventory, not proof that all APIs work at runtime.
