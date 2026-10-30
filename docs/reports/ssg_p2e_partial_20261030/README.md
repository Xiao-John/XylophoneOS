# P2E partial progress — NOT QUALIFIED

The original P2D evidence remains unchanged. This directory records separate
runs, not an independent completeness oracle or an acceptance of P2E.

* OBSERVED: `observation/` used the supplied system image, session, newly built
  Browser and existing Consumer, with SHA-256 values in `report.json`. Five
  real pipe responses contained 8, 8, 8, 8, 0 nodes. The last response reported
  `traversalComplete=true`, `hasData=false`, `hasNext=false` and
  `stopReason=EXHAUSTED`. These are Provider claims, not independent proof.
  Display-service resource counters before and after the children exited were
  equal. The ESC input was sent after paging and is not a responsiveness test.
* FAILED: `failed-newline/` retains an earlier probe timeout caused by waiting
  for session exit before closing Browser. Its fixture included a trailing
  newline and the Consumer observed 33 nodes. The fixture bytes and frames are
  retained. This is not a successful completeness test.
* NOT_RUN: independent source/Gumbo/liteHTML oracle; render-fragment and input
  hit verification; complete baseline collector and Consumer-computed Diff;
  interactive invalidation/resynchronization; cursor lifecycle and exhaustion
  tests; Notes safety work. Gate A, B and C remain unqualified.

The new response fields describe this page and traversal only. They do not
certify that all text or rendered fragments are complete. The 4096-ID boundary
fix is code-reviewed and compiled but its boundary behavior is NOT_RUN.
The observation and Browser regression overlapped briefly; no latency or
performance conclusion is drawn. No GitHub CI result is asserted.

Reproduce with `tests/ssg_browser_pages_probe.py --help`. All six inputs are
explicit, and each run requires a new output directory. The report records
input and QEMU executable hashes, command, serial output, and individual IPC
frames. A matching XOS runtime, QEMU and SDK-built executables are still needed.

* PASSED_SCOPED: `browser-regression/` is the existing nonpaged Browser IPC
  scenario, including its real scroll and reload checks and permission guards;
  it does not exercise paged baselines or prove P2E. The Notes/P1 pipe suite result is recorded separately below.

* FAILED: `large-regression/` reruns the original large-page Browser test
  without changing its assertions. DOM/layout and engine-hit checks passed;
  the original nonpaged scroll Diff assertion failed again. It overlapped the
  P1 guest run, so timing cannot be compared with earlier runs.

* PASSED_SCOPED: `p1-regression/` records the existing P1 pipe and small
  Browser guest checks, including timeout and cleanup. It is not a test of
  pagination or the independent Notes PR #9 safety work.
