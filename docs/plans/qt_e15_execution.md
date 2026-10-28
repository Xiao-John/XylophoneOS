# E15 QtBase implementation and qualification record

Baseline: upstream main `244ac40bbf4e4fb7743c51bc5ece0bd9fec594de`, branch
`codex/qt6-e15`. This document records the working plan; scoped G01/G03 qualification is in [0064](../work_log/0064_qt_e15_qualification.md).
Ownership: Qt port, private build inputs and Qt fixtures; shared ABI is not claimed.
The upstream open coordination issues #6 and #7 had no replies at inspection.

## Selection and boundaries

Use QtBase 6.8.3, tag `v6.8.3` commit `c07c2d5a527a644d36e7853d55132ae38921682f`.
The official archive and SHA-256 are locked in `src/ports/qt6/source_lock.json`.
This stable Qt 6 LTS line supplies QtCore, Gui and Widgets together without
fetching the whole Qt ecosystem. The target configuration and scoped guest functionality passed; full member license audit and redistribution qualification remain open. Security updates require a separately reviewed
version/patch update, not silently changing this lock.

First configure static QtCore with threads, event loop, timer, file and resource
support; verify Qt's own exception policy separately from application exceptions and RTTI; disable GUI, network, SQL, OpenGL, DBus,
ICU and tests/examples in the initial target. Feature names and effective values
must be taken from actual Qt configure output; requested flags are not proof.
QtGui raster and Widgets come only after G03. Host `moc`, `rcc` and other needed
build tools must come from the same source version; only cross-compiled target
libraries and ELF execute on XOS. Native building Qt inside XOS is a separate gate.

Target is x86_64 ELF, GCC 16.2, C++17 minimum, static threading SDK/newlib and
libstdc++; local-exec TLS, no red zone, matching CRT/linker and SDK manifest.
C++ exceptions, RTTI, aligned allocation, initialization/destruction and TLS,
pthread mutex/condition/thread exit must be tested on the exact new image. A
compile-only CMake try-compile cannot qualify linking or execution. The XOS toolchain and platform selection are qualified only for the recorded static QtCore profile.

## Event and I/O contract

Qt 6.8.3 `qeventdispatcher_unix.cpp` constructs an eventfd or nonblocking pipe
and calls `qt_safe_poll`; `qcore_unix.cpp` calls poll/ppoll or select fallback.
XOS `wait_word` plus display wait does not supply that multi-object contract.
The user-space dispatcher handles posted events, timers and cross-thread wake
using a coalescing atomic wait word and absolute monotonic deadline. Guest tests
cover bounded race and shutdown cases; socket notifiers are rejected, and file
or display readiness is not multiplexed. If G04
requires combining display and cross-thread wake, specify a generic mechanism,
claim a registry entry before implementing it and review existing consumers.
No Qt-specific kernel syscall. Validate check/sleep atomicity, deadline rollover,
wake-before-sleep, simultaneous wake/timeout, teardown and idle blocking in guest.

The existing `mmap`/`munmap` report ENOSYS; Qt uses buffered resource/translator fallbacks and file mapping fails explicitly. File service paths
are limited to its actual supported names and semantics; resource paths use real
rcc-generated data. Test EOF/short reads, missing/read-only/full disk, sync and
restart with disposable images. No assumption of network, locale, symlinks,
process signals, shared libraries, complete poll or multi-window behavior.

G04 maps QPA screen/window/backing store to the existing single exclusive
XRGB8888 surface and actual stride; Qt raster paints client RAM, `display_client`
submits dirty regions. PS/2 conversion, focus, resync on queue overflow, display
loss and teardown are required. Font implementation and licensing are to be chosen
against a real QtGui build. No BIOS/framebuffer access from Qt. G05 adds a real
Widgets editor and persistent file/error tests; G06 QML and G07 Quick are distinct
and contingent on their own budgets and gates.

Initial resource ceiling for evaluation is the existing single-CPU 512 MiB QEMU
configuration and four threads per process; measure actual heap, stacks, image,
idle scheduling and recovery before freezing a smaller deployment budget. Host
build uses a private directory and bounded concurrency; no shared cache cleanup.

## License and validation

QtBase contains LGPL-3.0-only, GPL and other separately licensed material; audit
actual enabled components and bundled dependencies, retain their license files,
source, patches and hashes. Static distribution requires a separately verified
compliance path including relinkable materials and notices; no release is implied.

G01 requires target ABI/threads/dependency probes and exact feature/SDK/build
provenance. G03 requires actual target QtCore app and error/recovery checks; the
fixture in `tests/fixtures/qt6` is only a starting point. G02 on 65/66, T0–T2,
Dash C1–C3, native compiler, file/persistence and affected Python/SDK must be
requalified against the final code and matching artifacts. Record PASSED, FAILED,
BLOCKED and NOT_RUN separately. G04/G05 cannot pass before dependencies pass.
