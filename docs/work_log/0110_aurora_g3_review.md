# 0110 — Aurora SDK / SSG / Desktop review and combination

2026-10-30. Re-fetched upstream and fork, read the three independent PR diffs,
their review/comment state, contracts, design, LocalPilot plan and frozen
evidence. SDK → SSG → Desktop remain open drafts without maintainer approval;
no branch was merged or rewritten. All 260 frozen evidence-index hashes match.

Two SDK corrections, one Browser correction, a scoped pipe probe and a host-only
temporal model have separate draft PRs. A local combination was built against the
unchanged one-core/512 MiB image and, after retained failures/reruns, passed 15
affected guest suites / 107 top-level checks. The original complete-tree semantic
fixture failed once for an unrecorded cause; a later explicitly complete targeted
fixture passed. Four desktop runners initially stopped at an old receipt mismatch;
the recompiled non-Aurora ELF matched its old SHA exactly and reruns passed.

[Review and evidence](../reports/aurora_g3_review_20261030/README.md) contains
the precise source combination, actual QEMU/build commands, raw serial/PPM,
hashes, findings, metrics and unsupported claims. No kernel, public system ABI,
QPA, driver or formal LocalPilot installation changes. Re-review, synchronize and
rerun affected guests after each accepted upstream dependency; multiwindow,
production Broker and real video perception remain separate unfinished work.
