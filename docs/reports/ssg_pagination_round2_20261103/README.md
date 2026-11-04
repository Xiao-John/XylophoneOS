# Pagination on current main

The system, normal Browser, separate test-only Oracle Browser, session,
consumer and Notes were rebuilt on main `48882c9` and current #48. Real
QEMU matched the independent structure/text Oracle for both fixed-document
baselines (34 pages and 267 nodes each). A separate verifier checked the
A/B diff and resource counters; the guest also followed one Consumer-selected
link using real PS/2 input. Notes long-Unicode Range and cleanup passed 2/2
on the combined source. The normal Browser was built without the Oracle.

[Results](round2_guest.json) bind these runs to the tested images, payloads
and runners. The initial invocation was rejected before boot because the
host paths lacked explicit receipt mappings; the successful guest run
used those mappings without bypassing the public-path gate.

Overall Gate A remains **NOT_QUALIFIED**. Gates B/C are **NOT_RUN** for
this build. This is fixed-fixture coverage, not general pagination,
performance, or complete cross-process requalification.
