# 0111 Aurora SDK maintainer-review fixes (author re-verification)

2026-10-30. Repairs for the five requested changes on upstream PR #29. The work
started from the PR head `758dde49d312277135fb2fa51887c2b4a94d6761`, fetched the
latest upstream `main` at `860405018c3f200b39efbe442147e89a3d2a399e`, merged that
base without rewriting the PR branch, then applied the review fixes. Current code
head before this evidence commit: `645d3e9fccb7edc7af6cf4882a82c9d3f7b95508`.

## Review resolutions

1. **Constitution and authorization.** Restored `docs/xos_plan.md` byte-for-byte
   from fetched `main`, including its C04 and D01/D02 entries. The active state
   now describes AI-native work as optional userland research. Added a traceable
   erratum to work log 0102; frozen qualification files and their original text
   remain unchanged. AI-native, SSG and LocalPilot remain research directions,
   not approved constitutional amendments or an activation of deferred D01/D02.
2. **Semantics callback lifetime.** `execute()` copies the indexed widget into an
   independent `QPointer` before calling `setText()` and does not touch the
   `Entry` after dispatch. It returns `VERIFIED_LOCAL` only after reading the
   requested text from the still-live target; destroyed or unreadable targets
   return `UNKNOWN`. The real Qt fixture forces entry-vector growth from a
   synchronous `textChanged` handler, checks immediate target destruction and
   `deleteLater()` completion after the callback, and verifies the new value.
3. **Semantics owner identity.** Copy and move construction/assignment are
   deleted. Compile-time type-trait assertions cover all four operations. Guest
   checks cover revocation, zero-TTL expiry, one-shot reuse, stale state, changed
   proposal binding, target destruction, and a newly exposed replacement target.
   This is a process-local API lifetime fix; it is not an OS isolation claim.
4. **SSG and Qt fixes.** Reused the implementation commits from fork PR #3
   (`8120215`) and PR #4 (`3995120`), plus their targeted fixture/evidence commits
   (`c5b122a`, `8197004`, `7a362ae`). The SSG path resets on capped or changed
   query scope, includes metadata, rejects missing/duplicate IDs, and reports
   removals as leaving the query result. The Qt path preserves standard button
   icons/mnemonics and explicit line-edit palettes during theme refresh. Only
   these SDK fixes and their tests were selected; the Desktop/Browser branches
   were not included. Fork PRs #3/#4 remain untouched and open; their fixes are
   recorded as absorbed into #29, pending maintainer disposition after #29.
5. **Independent current-source verification.** `docs/reports/aurora_sdk_review_20261030/`
   records current ELF builds, exact input hashes, QEMU guest outputs and resource
   counts. No #32 aggregate pass is used.

## Verification summary

- Semantics: 31 named checks pass under xsh and 31 under the real dash C3 ELF,
  including callback-triggered QVector growth, deferred deletion, target
  replacement, grant reuse/revocation/expiry/state changes, SSG redaction and
  SSG invalidation. Both runs return to the same active resource tuple
  `[130235, 3, 1]`; final service cleanup returns to baseline `[130279, 2, 0]`.
- Fork #3 SSG diff fixture: all 12 checks pass under xsh and dash; both return to
  `[130279, 2, 0]`. Cases include complete and capped snapshots, query-scope
  changes, metadata-only updates, duplicate/missing IDs, and true removals.
- Fork #4 controls fixture: icon, explicit-palette preservation and painted color
  pass under xsh and dash; final resource tuple returns to `[130279, 2, 0]`.
- SDK Semantics, SSG, style and theme sources were rebuilt and linked into the
  three current target ELFs. The available environment lacked host Qt `moc`/`rcc`
  executables; the build receipts identify the unchanged QPA, font and Qt resource
  objects reused from the matching Qt 6.8.3 guest build. All changed Aurora source
  was freshly compiled. Guest image SHA-256 is recorded in the report.
- This PR changes no kernel source or public system ABI files. No merge or Release
  was performed; the PR remains subject to maintainer review.

Full per-check reports, build receipts, serial logs, QEMU stderr logs, scanouts,
resource counters and SHA-256 index are in the linked review evidence directory.
