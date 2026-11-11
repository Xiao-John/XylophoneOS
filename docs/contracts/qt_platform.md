# Qt Port and System-Foundation Integration Contract

2026-10-28. This document registers interface ownership and requirements. The constrained
QtCore guest qualification is summarized below; this contract does not freeze C functions
or ABIs that have not yet been designed. Qt version, modules, features, tools, and resource
budgets are selected at G01, so this contract is not a guarantee for arbitrary Qt versions.

## Ownership Register

| Capability | Provider / current status | Qt responsibility and next qualification |
|---|---|---|
| C++ / pthread / TLS | Toolchain and threading workstreams; T0-T2, T3-PY, and constrained Qt QThread tests have separate evidence | Qt configuration and QThread/mutex/condition/exit probes; do not duplicate the thread library or use no-op locks |
| Monotonic / wall clock | Clock SDK; constrained evidence exists for monotonic waits and PY3 B2 wall clock | QtCore timers/timeouts and actual resolution; wake deadlines must not be replaced by wall-clock adjustments |
| Event readiness / wakeup | Constrained QtCore posted events, monotonic timers, and cross-thread wakeups have passed in guest; general multi-object poll/select is not implemented | E16 combines an input thread blocked outside the lock with Qt queued wakeups; no general poll/select, busy polling, or false FD readiness |
| Display / input | Display workstream; display_client, 65/66, one surface/focus, CPU raster, and PS/2 | QPA integration/screen/window/backing store/input; read actual mode/stride and render in client RAM, without direct MMIO/BIOS |
| Memory / mapping | Memory workstream; heap/page budgets exist, VMA/mmap/mprotect are not implemented | List actual calls and valid fallbacks; provide a minimal failure probe; do not add a Qt-specific kernel mmap path |
| Files / paths | File service and libc; constrained FDs/paths exist, permissions/links/full locale do not | QtCore I/O/resources/errors; state the ASCII path boundary clearly; UTF-8 content does not imply Unicode filename support |
| Network / terminal / dynamic loading | Owned by their respective foundation workstreams; no full compatibility qualification | Do not require all features for the first window; disabled features must be visible and recorded against actual consumers, not reported as success |
| moc/rcc/uic and other generators | Porting workstream | The first port may generate on the host with matching versions and cross-build; target-side regeneration is a separate G10 test |

## Interface Boundaries

- The kernel provides generic mechanisms only. It contains no Qt classes, object names,
  program-name privileges, or Qt-specific syscalls.
- The porting workstream owns the user-space QtCore platform adaptation and QPA plugin.
  It creates a Qt port directory under `src/ports/` when implementation begins. The display
  workstream owns the display service/SDK, the threading workstream owns pthread, and the
  integration lead owns shared libc/dispatch changes.
- Every SDK capability needs a version, size/layout, return convention, error and
  cancellation/timeout behavior, object lifecycle, concurrency rules, and quotas. The
  provider's contract must freeze the ABI. A requirement in this table is not itself a
  header declaration.
- Validate source buffers and regions before display calls. Qt must not assume zero-copy,
  direct framebuffer mapping, or an arbitrary number of windows. Input sequence/loss
  resynchronization, focus, client/service death, and wait wakeups follow the display contract.
- A request to change single-surface policy, waiting, shared mappings, or object-revocation
  semantics must describe the new contract and affected old consumers first. Do not silently
  change foundation behavior in a QPA patch or use a new number to bypass compatibility and
  identity checks.

## Parallel Work Process

1. Register the owner, branch, file scope, and minimum gate in `state` before work begins.
   Do not assume another agent is active without an entry.
2. Qt porting changes only the port, platform adaptation, its build, and its fixtures. When
   a foundation capability is missing, submit the call site, inputs, errors, and expected behavior.
3. Register syscall numbers and service operations in `abi_registry.md` first. The owner
   responsible for that interface integrates public headers, manifests, and dispatch.
   Reserved number ranges prevent cross-module collisions, but each operation still needs
   an entry. Do not claim fixed PID/endpoint values.
4. Use private output directories and fixed SDK/build inputs; shared `build` use is exclusive.
   Old G02/T2/Python results apply only to their recorded inputs.
5. Qualify QtCore G03, first window G04, Widgets G05, QML G06, and Quick G07 separately.
   Distinguish not implemented, not run, and failed.

E15 merged in PR #8 (`7a7481f`) and E16 merged in PR #9 (`be1e9c1`). Any new combination
must record its own inputs and qualification.

## E15 Constrained Implementation and Qualification

`codex/qt6-e15` uses a single-consumer coalescing wait-word for posted events and monotonic
timers. FD/socket notifiers are rejected and cannot be multiplexed with display waits.
QMutex uses pthread monotonic condition variables. QThread cancellation, mappings, path
canonicalization, UID permissions, and no-overwrite rename are unsupported. See
[0063](../work_log/0063_qt_e15_continuation.md) for source, race/lifecycle limits, and guest
candidate evidence. Constrained G01/G03 features passed; see
[0064](../work_log/0064_qt_e15_qualification.md). Absolute peak memory and release audits
remain incomplete. This does not open new ABIs or qualify poll support. Follow-up tests for
blocked-boundary posting, spurious wakeups/absolute deadlines, and active timer-worker exit
on the same frozen implementation are in [0065](../work_log/0065_qt_e15_lifecycle_recheck.md);
they add no public mechanism and change no ABI.

## E16 Constrained QPA Contract

The static Qt 6.8.3 `xos` platform plugin reads the actual display mode/stride, renders to a
user-space RGB32 QImage, clips QRegion, and synchronously presents through Display Service.
There is no MMIO mapping or program-name authorization. One exclusive full-screen Surface
is supported. A second window reports connect=-16 and exits; nonzero flush offsets and child
windows are unsupported.

Requests/replies on one display_client are serialized by QMutex. Input uses an SDK joinable
pthread. `wait_input()` does not hold the transaction lock; after reading input it posts a
task to a QObject on the GUI thread, which calls QWindowSystemInterface. Shutdown sets the
stop flag, disconnects to wake the input wait, joins the pthread, then clears the delivery
target. Service death returns -19 and exits with status 72; a new client can recover after
the service restarts. Normal use has two threads and remains within the per-process limit of
four. No syscall 65/66 or display wire v1 changes were made.

In Qt 6.8.3, the detached-thread cleanup notification used by QThread::wait may precede
kernel-thread exit. E16 leaves E15 unchanged and uses pthread_join for complete input-thread
reclamation. Hiding the window triggers Qt focus loss and suppresses GUI input, but the
exclusive Surface remains until destruction. Supported input is Set1 English, Shift/Ctrl/Alt/
Caps, three mouse buttons, sequencing, and 64-entry overflow resync. IME, wheel, USB, and
multi-window composition are absent. The original DejaVu font is rendered through FreeType/
HarfBuzz/QPainter. See the [E16 implementation](../plans/qt_e16_execution.md) and
[0066](../work_log/0066_qt_e16_qualification.md) for implementation, failures, and qualification.
Static distribution and per-member license reviews remain incomplete.

## E17 Widgets / Aurora Constrained Contract

Cross-compile Core/Gui/Widgets with the same newly built SDK/C++ runtime and frozen QtBase
6.8.3; do not mix in the old E15 archives. Retain the original E15/E16 build entry points
and frozen reports. Widgets child controls, viewport, and scrolling were tested with the
top-level backing store and zero offset. Existing child/native, nonzero flush-offset, and
second-top-level rejection semantics are unchanged. QPA adds only Home/End/PageUp/PageDown/
Delete Set1 mapping and flush observation; there are no new syscalls or display-wire changes.

`libXosAurora.a` provides `aurora::initialize(QApplication&)`, selecting QProxyStyle/QPalette
and a dark style for standard buttons, text, and input. Canvas/panel/button are optional shared
controls. Its bounded low-frequency blur, environment blending, and software pointer are
application-local; they are not a system compositor, cross-application refraction, or GPU
acceleration. The QtGui image/paint thread pool may add one thread; observed usage is commonly
three threads and remains within the four-thread quota. Do not transfer E16's two-thread result
to Widgets. Process resources were checked after normal exit, kill, fault, and service failure.

Saving reuses file wire-v2 staging/journal. Read-only checks use a non-truncating writable
open followed by close. QFile is used for reading/comparison, not WriteOnly truncation of the
target; QSaveFile does not promise safe overwrite. Pre-commit errors preserve the target.
Commit/final-sync errors yield UNKNOWN, retain the buffer, and block retry. Comparing old
content in the consumer is not concurrent CAS. Do not claim all errors preserve the old path,
arbitrary power-loss safety, or protection from torn sectors. Actual error paths, injection
layers, post-reboot byte comparisons, and limits are documented in
[0078](../work_log/0078_qt_e17_aurora_qualification.md).

G05/Aurora 仅对冻结夹具和已声明范围通过；静态分发/完整许可/重链接、绝对峰值、
CPU、长期压力、完整 Unicode 字体、IME/剪贴板、QML/Quick 均没有继承资格。
复现见 [E17 实施](../plans/qt_e17_implementation.md)。

## 2026-10-30 Aurora v2 / application-local SSG

The opt-in static Aurora library now has tokens v2, native materials, accessibility
and quality fallback, independent standard-Widgets consumers and an app-local
SSG/Intent prototype. See [SDK work log](../work_log/0102_aurora_ui_v2_sdk.md),
[SSG contract](semantic_scene_graph.md) and [consumer qualification](../work_log/0103_aurora_ssg_consumers.md).
No QtCore/Gui/QPA source, system ABI or kernel file changed. Legacy non-Aurora
Widgets remain byte-identical to the archived E17 probe and run on the new image.
The E17 dark Canvas/Panel consumers have not acquired global live theme migration.

The single-Surface desktop/session is a separate userland consumer, not a new
QPA window transport: [G1](../work_log/0104_aurora_desktop_shell.md). Native popup
windows, cross-process themes/SSG, window composition and modern WebView remain
explicitly unavailable/proposed. The proposed transport requires independent
review before implementation; no new number/opcode is allocated.
