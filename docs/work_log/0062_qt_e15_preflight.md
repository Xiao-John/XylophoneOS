# 0062 E15 Qt preflight — incomplete, 2026-10-28

Scope: `codex/qt6-e15` from upstream `244ac40bbf4e4fb7743c51bc5ece0bd9fec594de`;
no ABI allocation. Public PR #3/#4/#5 merged, issues #6/#7 had no comments and
no open PR existed when checked. This is an exploratory draft, not E15/G01/G03.
`src/user/threading/compile.py` is a shared SDK change included for integrator
review: its C++ include order failed `#include_next <stdlib.h>`; the fixed order
and `-nostdinc++` use only the matching SDK headers. No changes to another
worktree, daily disk, or shared build were required.

## Actual executions

- **PASSED** source archive SHA-256 `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`, official QtBase 6.8.3; `prepare_source.py` extracted and patched a private tree, and refuses an existing destination. Tag resolves to `c07c2d5a527a644d36e7853d55132ae38921682f`.
- **PASSED, host only** QtBase host build with Apple Clang 21/SDK 27, CMake 4.4.4/Ninja 1.13.2. Initial builds failed `__yield` undeclared; retry used `-include arm_acle.h` for C/C++/ObjC/ObjC++ and the documented warning override for command-line-tools-only Xcode detection. `moc 6.8.3` SHA-256 `6ab35b238fef41dab4dc4c425f92710cc76dc099d4bc54ba29c9152e332c2793`; `rcc 6.8.3` SHA-256 `63c711e483fa2b6bf1f478add86ff5e8235302b2a119bb0d7b7e4b68bc1cacff`. Both generated fixture sources; this is not target execution.
- **PASSED, SDK probe only**: rebuilt SDK manifest SHA-256 `17aface53dc89dbbea6c059ec4984fecbdc9857dcede001522105122104ba552`, compiled `tests/fixtures/threading/cpp_probe.cpp` through corrected SDK entry to ELF SHA-256 `2a48c27955fd7c53984e4fa4c83c7d180ca84d25c42570880e872d4832f7e4c7`. On QEMU 11.1.2 TCG, i440fx, 1 CPU, 512 MiB, `qemu64,+rdrand`, guest exited 0, printed the C++ thread/mutex/condition/TLS/exception marker, and process resource counters returned `[130322,2,0]` to baseline. Image `xos.img` SHA-256 `af416620f04bea9462325310de0b403b6f3086ae747dbc61d9d816f589663d8f`, system manifest SHA-256 `f54fcd97c743fe061577f461ac9bf6d704d28f1f5c480875c2c3dd65413edc27`, build ID `000f3718fdbf344e`. The system build preceded the compile-script fix; the kernel sources were unchanged by that fix, but this is not a final commit-bound qualification. See `../reports/qt_e15_preflight_20261028/` for command, guest serial and raw failures.
- **FAILED, target Qt build**: target 6.8.3 compiled bundled PCRE2 and zlib, plus some QtCore objects; no QtCore archive or Qt executable. First PCRE2 JIT failed on `sys/mman.h`; rebuild disabled JIT and built the PCRE2 archive. Qt platform definitions initially requested absent `sys/socket.h`; explicit `QT_NO_SOCKET_H` proceeds without claiming sockets. Generic CMake platform omitted Unix source and failed on `qcore_unix_p.h`; the XOS CMake platform selects Unix-derived files.
- **FAILED, truthful target configure**: generic CMake's compile-only try-check incorrectly reported `poll_select=ON`; it does not prove select links or works. With XOS platform and `FEATURE_poll_select=OFF`, configure explicitly fails `Qt requires poll(), ppoll(), poll_ts() or select()`. The old target7 summary is included solely as evidence of the unsafe false positive. All CMake feature checks require validation against real links and guest behavior before use.

## Reproduction and next entry

The locked source is prepared with `python3 src/ports/qt6/prepare_source.py ARCHIVE NEW_DIRECTORY`.
Host and target configure/build logs are under the worktree's private `build/qt_e15`;
compressed failure logs and guest serial are retained in the report directory.
Use `tests/qt6_sdk_probe.py --image IMAGE --payload ELF --report REPORT` with
`QEMU` pointing to the actual executable and a freshly built matching SDK. It
creates a disposable FAT disk. No CMake configure pass establishes ABI support.

Next implement and test a real Qt dispatcher using a race-safe wait-word and
monotonic deadline for the restricted posted-event/timer use case, or obtain a
reviewed generic wait facility if actual consumers require combined readiness.
Ensure the Qt configuration selects it without falsely advertising poll/select.
Then address compile/link errors, resource/FD semantics, guest idle/wakeup/exit
and license audit. `tests/fixtures/qt6/core_smoke.cpp` is incomplete G03 coverage.

**G01/G03/G04/G05: NOT_RUN, not passed.** E14 G02 at 65/66, full T0–T2,
Dash C1–C3, native GCC/G++, filesystem/persistence and affected Python/SDK
regressions on final changes: **NOT_RUN**. Memory peak/idle CPU, Qt and bundled
dependency license audit, redistributable relink materials: **NOT_RUN**. QtGui,
Widgets, QML, Quick and interactive Qt window: **NOT_RUN**. Historical gate
receipts remain bound to their original inputs.
