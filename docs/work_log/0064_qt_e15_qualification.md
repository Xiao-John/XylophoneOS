# 0064 E15 QtCore 6.8.3 scoped guest qualification

Implementation commit `892917626721e6e8e39bedbc046de841a01c07ff`; tested
system and principal fixture commit `b090d4532ff5aa19ec5290da16863154c7d08860`,
from upstream `244ac40bbf4e4fb7743c51bc5ece0bd9fec594de`. The supplemental
QMutex/interrupt fixture sources and their hashes are included with this evidence.
This report commit changes docs and frozen evidence only. The system manifest binds 565 source inputs to build
`48e5e73bcd649f44`; all were rehashed after the fixture commit. The threading
SDK's recorded source inputs were separately rehashed and matched. QtBase was
re-extracted from the locked official archive, patched, built out of tree, then
re-extracted and recursively compared byte-for-byte: no differences.

**G01: PASSED, scoped functional profile. G03: PASSED, scoped functional
profile. Distribution qualification: NOT_RUN.** Details, commands, exact
artifact hashes, test JSON, compressed guest serial and configuration are in
[qualification.json](../reports/qt_e15_qualified_20261028/qualification.json).
The QtCore archive SHA-256 is `d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3`;
the XOS floppy image SHA-256 is
`8d46f18a2a4255b8df8e251cce23962e654bcced3b6357cfab95b5a6649bbdaf`.
The SDK manifest SHA-256 is
`2e5a53ac965fd626eeefed070f3027ff7a11f82fe6d19a94c75e97003547e50c`.
Both QtCore and the application ELFs are actual x86-64 XOS builds, not host Qt.
Static archive undefined-symbol inventory against the selected Qt/SDK archives
leaves only linker-provided `_GLOBAL_OFFSET_TABLE_`; the real applications also
linked with `--no-undefined`. This inventory does not validate unexercised APIs.

The fixed profile is static QtCore with threads, timers, QObject and file/resource
support, bundled PCRE2 10.45 (JIT disabled), Qt zlib 1.3.1, double-conversion 3.3.0 and SHA3. QtGui,
Network, Widgets, QtXml, QtConcurrent, QtTest, dynamic loading, process APIs,
filesystem watchers, shared memory, system semaphores and poll/select are disabled.
QtCore is built with `-fexceptions`; application C++17 exceptions, RTTI,
over-aligned allocation, static initialization, TLS destructors and std::thread
were tested separately in a real Qt-linked guest ELF. Host moc/rcc are 6.8.3;
CMake 4.4.4/Ninja 1.13.2; target GCC 16.2.0; QEMU 11.1.2 TCG i440fx,
`qemu64,+rdrand`, 1 CPU, 512 MiB.

G03 guest tests include three independent QCoreApplication/resource/queued-slot
runs; nested event loops, 32 posted events, standalone interrupt, notifier
rejection, monotonic timer expiry and cancellation, QThread, contended QMutex,
QWaitCondition timeout/wake, wake-before-wait and timeout/wake races, thread
quota refusal, invalid wait address, worker-alive process fault and resource
recovery. QFile/QIODevice/QDir exercised content, short read/EOF, missing file,
read-only FAT attribute and synthetic full FAT error, then sync/reboot/Qt readback.
Every test checked exit/fault outcome and resource baseline. The gate implements
no FD readiness and does not claim direct `pthread_exit` from a Qt worker or
thread cancellation. Timer granularity and single-core behavior follow XOS.

The test machine has 512 MiB; XOS admits at most 65,536 user pages per process,
4 threads per process and default 256 KiB worker stacks. A 4 MiB Qt allocation
workload sampled a high-water of 2,122 user pages (8,691,712 bytes) over ten
10 ms samples; **the absolute peak is NOT_RUN**, and this measurement is not a
limit or a guarantee for all Qt workloads. During idle event waiting, kernel
thread statistics showed a blocked waiter; CPU percentage was not measured.
Thread quota exhaustion and the existing T0 ENOMEM rollback probe passed; broad
Qt allocation exhaustion and long randomized stress are NOT_RUN.

Current-source regression: G02 19 groups; display compatibility 5; T0–T2
15+10+10; file/persistence 8+4; native GCC/G++ 6; task/process/libc/runtime
12+13+3+5; Dash C1 24, C2 30, C3 66 and C3 exec 16. CPython T3 5 groups
passed on this image using an existing interpreter stage whose 560 files were
hash-verified; this is not a CPython rebuild against the new SDK or full Python
extension qualification. Old reports remain untouched. First display-compat
invocation omitted mandatory arguments and the first sbase attempts lacked
source/used a host assembler; raw failures are retained, and corrected runs
passed.

Qt source preparation: `python3 src/ports/qt6/prepare_source.py ARCHIVE NEW_DIR`.
Target build: `python3 src/ports/qt6/configure_target.py --source NEW_DIR --build
BUILD --sdk THREAD_SDK --binutils TARGET_TOOLS --host-qt HOST_QT`, followed by
`cmake --build BUILD --target Core --parallel 4`. Use
`src/ports/qt6/build_fixture.py --help` and the recorded fixture receipts for
exact target compiler/linker commands. QEMU test runner commands and disk setup
are in the checked-in tests and reports. Builds are under this worktree's
`build/qt_e15`; no daily disk was used.

Licenses for Qt and selected bundled libraries are recorded and materials audit
passed, but individual archive-member attribution, security review, and static
relinkable-object/source distribution obligations remain NOT_RUN. Do not ship a
Qt binary on this evidence alone. No QtGui, QPA, Widgets, QML, Quick, full POSIX,
network, Unicode filenames, thread cancellation, exact memory peak, SMP or long
stress claim is made. E16/G04 must separately solve display-input and event
wakeup integration without assuming the G03 wait word multiplexes FD/display.
