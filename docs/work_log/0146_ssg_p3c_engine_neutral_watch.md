# 0146 — SSG P3C bounded observation

2026-10-31. This branch is stacked on unmerged P3B PR #11 and its Browser PR #10
dependency. It does not merge either branch. Upstream main was checked at
`94549a93f9bde9c86c3f2d863e29a2dbd552f7de`; the WebKit work visible there is a
plan, not a port or M0 receipt.

The source changes are the private provider contract, generic watch scheduler,
Browser and Notes compatibility adapters, scoped source events, and the
supervisor's bounded watch/control path. Existing page and UTF-16 range wire
protocols are reused. No kernel, ABI, QPA, driver, clock, IRQ, scheduler,
global permission or LocalPilot change is included. Scope, bounds, capability
differences, freshness and failure semantics are in
[the P3C contract](../contracts/ssg_p3c_watch.md).

The final target build uses the unchanged P3B guest image, SDK, Qt libraries,
and Browser/Notes binaries with newly cross-built supervisor and contract-test
ELFs. The target source hashes, compiler and SDK receipts are in the build
manifest; the framed retry target source bytes match commit
`4eb79a623b25c5ba3fe1addb9d6dba436a05e549`. The README gives portable commands
and exact evidence references.
The preceding build's 27 contract checks and complete targeted watch suite passed;
the framed retry build passed 32 contract checks, targeted capped-fault tests
and its full targeted suite. The ordinary three-program run was
observed without a per-run IPC/DOM oracle. The separate affected Browser,
Notes and P1 regressions passed, and the final supervisor passed its legacy
P3B compatibility suite.

Review found that stopping during a later incomplete pair could leave the
previous complete aggregate label in the final summary. The scheduler now marks
that interrupted pair partial, and both a synthetic contract check and the real
in-flight cancellation case exercise the corrected behavior.

The preceding stress run had one capped Notes snapshot. The current adapter
retries only explicitly capped provisional snapshots, at most twice within the
same source budget; persistent caps remain unknown. A subsequent test exposed
interleaving inside a long console event line. Current events use bounded,
length- and sequence-checked records, each written in one console syscall;
an independent decoder rejects incomplete streams. Test-only fault fixtures
confirmed one-shot recovery, persistent-cap unknown status and actual interleaved noise.
These records are not an authenticated or durable subscriber transport.

Two earlier Notes shutdown failures were observed and retained: after EOF,
Notes did not exit before the supervisor's 20-second bound and was killed;
resource samples returned to baseline. Each failed case passed on a fresh retry.
Eight instrumented original and eight native-join candidate sessions did not
reproduce either failure; the candidate was not adopted. This is separate
from, and not proven to explain, the prior Consumer exit timeout.
`EXIT_RACE_ROOT_CAUSE=UNRESOLVED`.

The event stream is currently console-only; a pipe-backed stdout is refused
because the existing libc pipe write can wait without a deadline. Polling can
miss changes between samples, and the per-source observations are sequential:
`globalAtomicSnapshot=NOT_IMPLEMENTED`. There is no transparent source restart,
durable subscriber or claimed WebKit integration. SDK distribution material
qualification remains incomplete: `DISTRIBUTION_NOT_QUALIFIED`.

The isolated final-build stress completed 24/24 controlled sessions; the prior
build's 23/24 and its capped snapshot remain failures in the evidence. A partial
cost comparison found 88 requests and approximately 301.7 KB of actual IPC in
each two-observation path; a separate full-baseline mode and CPU/peak-memory
measurement were not run. Exported evidence passed 73 host replay checks; the
final public scan is recorded in the
[P3C report](../reports/ssg_p3c_engine_neutral_20261031/README.md).
Remaining work includes an independently bounded consumer event
transport, source reconnect/supervisor policy, reproduction and root-cause
isolation of shutdown failures, and the actual WebKit M0–M5 port. A passing
synthetic adapter test is not a WebKit integration result.
