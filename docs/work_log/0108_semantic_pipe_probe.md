# 0108 — Semantic Broker transport feasibility

2026-10-30, independent branch at upstream `3377dbf`. The only executable is a
synthetic 16-byte parent/child pipe probe; no kernel, public ABI, driver, file
service or production SSG interface is changed. The accompanying broker and
LocalPilot consumer documents are proposals with explicit identity, permissions,
quotas, revocation, lifecycle, timestamps and UNKNOWN boundaries.

Built using the manifest-checked E17 SDK `compile.py` and ran
`tests/semantic_pipe_guest.py` on the frozen one-core/512 MiB QEMU image. xsh
with explicit delegation passed 12 checks including queue-full, close/EOF and
child exit; dash without child-spawn delegation produced the expected denial.
The actual commands, tool/image/payload hashes and serial log are in
[the report](../reports/semantic_broker_pipe_20261030/README.md). The synthetic
payload is not a Qt provider or broker and serial is only test evidence.

Generic endpoint creation to arbitrary running peers, authentication per
message, revoking other holders, dynamic discovery, multi-source deadline waits,
subscriptions and production permission decisions are not established. Next
review the generic mechanisms and, separately, a cooperating prewired provider
experiment; do not reuse file service rights or create a semantic-specific syscall.
