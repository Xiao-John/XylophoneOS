# 0105 — SSG Diff integrity review fix

2026-10-30. Independent SDK follow-up at parent `758dde49`; no kernel, public
system ABI, QPA or driver changes. Changed `SceneStream`/`QtScene`, the local
contract and focused guest fixture/runner. Truncation or query-scope changes now
require a reset; duplicate/missing IDs reject without replacing history; a diff
contains current metadata and labels removals as leaving the query result.

Built the exact target with the E17 SDK and Qt 6.8.3 using
`src/ports/qt6/build_widgets_fixture.py`; `tests/ssg_diff_guest.py` ran in xsh on
the frozen one-core/512 MiB QEMU image. Original SDK: 4/12 pass, 8 fail; final:
12/12 pass and exact resource return. Existing `tests/aurora_platform_guest.py
--case semantic` passed five guest gates and 25 local native assertions. Actual
QEMU/build commands, source/ELF/image hashes, failures and serial evidence are
in [the report](../reports/ssg_diff_integrity_20261030/README.md).

An initial harness timed out before fixture startup; the first repair faulted on
a temporary Qt JSON reference and was corrected. Neither failed run was relabeled.
Browser's mutable scroll metadata needs an explicit scope in its dependent PR;
new combined Notes/Browser/Desktop results cannot be inferred from these tests.
Cross-process observation/action, secure global identity and true allocator OOM
remain unimplemented or untested. After review, combine with the dependent SSG
change and rerun affected guest gates on each changed upstream baseline.

A combined-source semantic fixture subsequently failed its whole-tree diff
assertion once; the recorded run lacks enough detail to establish the cause.
A diagnostic rerun passed. The fixture now explicitly checks an uncapped,
role-filtered pair and the changed real target; it passed 26 native assertions
and five SDK-branch guest gates. See [new evidence](../reports/ssg_targeted_diff_20261030/README.md);
the affected combined-source rerun is a separate required gate.

The focused 12-check diff fixture was subsequently rerun under both xsh and
actual dash, with normal exit and exact resource return; see
[the dual-shell report](../reports/ssg_diff_dash_20261030/README.md).
