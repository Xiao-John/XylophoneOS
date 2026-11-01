# Application-local SSG diff integrity

Base SDK `758dde49d312277135fb2fa51887c2b4a94d6761`; frozen system image
SHA-256 `165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
The independent regression is a real xsh-launched Qt/XOS ELF under one-core,
512 MiB QEMU TCG. Reports include the actual QEMU command, ELF/image hashes,
checks and resource counts; receipts contain target build commands and input
hashes. `evidence.json` hashes the retained evidence and source inputs.

- `before`: original SDK produced **4 PASS / 8 FAIL** in 12 checks, including
  partial-result, query-scope and duplicate-ID cases. The fixture exited 1.
- `initial-harness-failure`: an earlier run timed out before the fixture began;
  it is retained as a harness failure, not a passing baseline. The rerun used
  `demo quiet` before launch.
- `first-fix-fault`: the first repair faulted inside `QJsonValueConstRef` after
  the first check due to a reference into a temporary JSON object. This failed
  run is preserved. The final implementation copies a `QJsonValue` instead.
- `final`: **12 / 12 PASS**, normal exit, and exact resource return.
- `semantic-regression`: the existing real Qt fixture ran its 25 native checks
  and five top-level guest checks, including local authorization/verification,
  killed process and resource return. This does not authorize cross-process use.

The fix prevents complete diffs across capped results or changed query scope,
returns current metadata, validates unique nonempty IDs and clarifies that
`removed` means only leaving a query result. Publishers without explicit
`queryScope` conservatively reset when metadata changes. Browser's scrolling
provider needs a separate dependent change to specify its stable query scope.
Notes and Browser combination regressions must be rerun after dependency changes;
the historical 15-suite result is not rebound to this new SDK.
