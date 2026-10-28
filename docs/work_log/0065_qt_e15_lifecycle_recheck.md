# 0065 E15 QtCore lifecycle and qualification recheck

2026-10-28, `codex/qt6-e15`, continuing Draft PR #8. The supplied handoff
`8c0402b` had already advanced to `0a7c614` when inspected. Upstream main still
resolved to `244ac40`; the remote PR HEAD matched the clean local branch, with
no review comments. The threading, Dash and display worktrees were clean.
No production runtime, public ABI, SDK, kernel or other worktree was changed.

**G01: PASSED, scoped functional profile. G03: PASSED, scoped functional
profile. Distribution qualification: NOT_RUN.** This supplements rather than
replaces [0064](0064_qt_e15_qualification.md). The original failures and previous
qualification remain bound to their recorded inputs. New raw evidence and
commands are in [the recheck index](../reports/qt_e15_recheck_20261028/summary.json).

## Verified inputs and actual guest executions

All ten recorded top-level artifacts, seven tool binaries, 565 system source
inputs, 66 threading SDK source inputs, 1,054 SDK artifacts, seven Qt fixture
receipts and 99 frozen evidence-package files matched their hashes. The patched
Qt source tree still matched its independent replay byte for byte. Building
the Core target reported `ninja: no work to do`; its complete 16,865,118-byte
archive remained SHA-256
`d9435accf464ff5f7fa6d668b59c77ed5f3b5da21f2a0f56de512794aab474d3`.
This is verification of an existing actual target build, not another configure
or host-tool preflight. Existing configure/build failure logs remain untouched.

The new `core_lifecycle.cpp` fixture links the real frozen QtCore and SDK. It
checks raw wait-word spurious wakes without changing the predicate and reuses
one absolute deadline; posts an event synchronously from `aboutToBlock` after
the dispatcher's queue check; and repeatedly exits a worker event loop with
an active repeating timer. Qt's finish path must deliver DeferredDelete,
destroy the timer owner and dispatcher, and restore thread/kernel-stack counts.
It uses at most the main thread plus one worker. Three independent guest
launches passed: 48 boundary deliveries and 24 worker timer/dispatcher teardowns.
The ELF SHA-256 is
`27bef682341ad241d2e84782c7c445ee7a96bf4dd174712fe2c1a21b4a59fc14`;
the receipt binds its exact fixture source, QtCore, resource and SDK inputs.

The new `tests/qt6_qualification_recheck.py` refuses an existing output directory,
checks the frozen inputs, then runs 16 real guest cases sequentially. All passed:
three smoke launches; wait/wake races; posted/nested/timer events; quota refusal;
worker-alive process fault; sync/reboot/Qt readback; read-only/full FAT errors;
C++/TLS/exception ABI; memory sampling; contended QMutex; interrupt without
posted events; and the three lifecycle launches. Every process test checked
its real exit/fault outcome and resource recovery. The lifecycle runs each
returned supervisor counters `[130322, 2, 0]` to baseline.

Fresh regressions in a separate output overlay passed G02 syscall 65/66 (19
groups), T0/T1 (15), pthread (10), C++ threads (10), file (8), and persistence
(4). Earlier Dash, native compiler, display-compatibility and CPython regression
reports were integrity-checked and retained on their original identical
production inputs; those suites were not rerun in this supplemental pass.

## Reproduction and limits

Build the new fixture through `src/ports/qt6/build_fixture.py`, using
`--source tests/fixtures/qt6/core_lifecycle.cpp`, the existing resource QRC,
`frozen_sdk`, `final_qt`, `host-install` and target binutils. The frozen
`core_lifecycle.receipt.json` contains the exact compile/link commands.
Then run with the recorded QEMU executable:

```sh
python3 tests/qt6_qualification_recheck.py \
  --qualification docs/reports/qt_e15_qualified_20261028/qualification.json \
  --lifecycle build/qt_e15/recheck_20261028/core_lifecycle_v2.elf \
  --report-dir build/qt_e15/recheck_20261028/NEW_GUEST_RUN
```

All new guest runs use the same single-core TCG 512 MiB image, build
`48e5e73bcd649f44`, and private disposable FAT disks. The fixture and runner
are new test inputs with their own hashes; this report does not silently
rebind old evidence to them. These bounded tests do not establish exhaustive
interleaving coverage, SMP, long stress, CPU percentage, absolute memory peak,
direct external pthread exit, FD multiplexing, or a redistributable Qt product.
Full member-license and static redistribution/relink review remains NOT_RUN.
PR #8 remains Draft for maintainer review; no merge or Release change.
