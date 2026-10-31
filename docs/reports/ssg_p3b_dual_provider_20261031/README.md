# P3B — dual-provider aggregation and isolation

This is a read-only, explicitly prewired userspace prototype. The supervisor
creates two independent request/response pipe pairs and starts Browser and Notes
as separate XOS children. Provider slots come from that wiring; self-reported
names, PIDs, JSON fields and model output do not grant access. There is no
production broker, arbitrary application discovery, executor, or desktop-wide
permission model. Each source independently defaults to text denial; the
trusted session caller must explicitly pass `--browser-text` and/or
`--notes-text`, and a corresponding
`--browser-denied` or `--notes-denied` takes precedence. No kernel, public ABI,
QPA, device driver, clock, IRQ, scheduler or global permission changes are included.

The PR is stacked on the unmerged Browser draft PR #10, base
`687b6b1fa2fa1600162843ab4b259511e817701f`. Required Notes text-range and
joinable-watchdog changes were selectively ported from PR #9, including
`13c4521`, `dd11218`, and `c9ff0bc`. Their historical reports and branches were
not merged or rewritten. The final target programs were built from source commit
`59291311956c82baa2afc22a18dab308abfa87f8`. The default-denial verifier was
strengthened afterward in `a0449bd`; that host-only change did not alter the
target programs. The portable affected-regression wrapper was introduced in
`98d7716` and corrected in host-only commit `8d29888` after a missing-input
variable caused an initial guest-regression setup failure.
The portable build manifest and source/tool/ELF hashes are included below.

## Status

| Acceptance | Result | Scope |
| --- | --- | --- |
| `P3B_DUAL_PROVIDER_BASELINE` | `PASSED_SCOPED` | Real guest, one supervisor, two live provider processes, two pipe pairs, independent checks. |
| `P3B_AGGREGATE_IDENTITY` | `PASSED_SCOPED` | Actual overlapping local IDs remain distinct; old instance and old pipe tokens refused. |
| `P3B_CROSS_APP_CHANGE_ISOLATION` | `PASSED_SCOPED` | Real Notes edit and Browser scroll in separate dual-source sessions with one hidden source. |
| `P3B_PROVIDER_PERMISSION_ISOLATION` | `PASSED_SCOPED` | Initial denial, mid-read revoke, document/ancestor protection, Browser revoke, and cross-pipe denial. |
| `P3B_PROCESS_FAILURE_CONTAINMENT` | `PASSED_SCOPED` | Independent guest cases covered both source exits, exit during a peer read, timeout, truncation, cancellation, replacement and revocation. |
| `P3B_CLEAN_SHUTDOWN_STRESS` | `PASSED_SCOPED` | 48/48 complete same-boot sessions; sampled resources returned to the active-display baseline. |
| `P3B_EXIT_RACE_ROOT_CAUSE` | `UNRESOLVED` | No root-cause proof; stress non-reproduction is not a fix proof. |
| `P3B_PUBLIC_EVIDENCE_SCAN` | `PASS` | Decoded payloads, archive members, staged change-set blobs and proposed PR body were scanned. |
| `P3B_GUEST_REGRESSIONS` | `PASS` | Affected Browser, Notes and P1 guest regressions passed after a targeted Notes boundary retry; the initial setup failure is preserved. |

`globalAtomicSnapshot = NOT_IMPLEMENTED`. Both source observations can be locally
complete while captured at different times. A baseline is a historical,
sequential observation, not a claim that the desktop had one simultaneous state.
Both complete sources report `UNVERIFIED_AFTER_OBSERVATION`; failed sources
report `NOT_CURRENT`. For the baseline run the Browser interval was
`10840000000–13680000000` ns and
Notes was `13680000000–13820000000` ns in that guest's monotonic clock domain.

## Observed dual-source behavior

- The guest supervisor received 34 Browser pages containing 267 nodes and a
  4,114-UTF-16-unit synthetic Notes document. The host independently rebuilt
  each stream, compared Browser parent/order/text/href to the test-only
  liteHTML model before and after traversal, and compared Notes to both the
  fixed input and its owner's digest. Browser and Notes had an actual equal
  local numeric node ID; the source/instance/epoch-qualified IDs differed.
- The ordinary supervisor and ordinary Notes also completed a two-sample
  source Diff with no raw IPC logging. A separate run with the ordinary Browser
  as well was **OBSERVED**, without a per-run DOM oracle; it is not promoted to
  independent structure qualification.
- A real PS/2 Notes edit invalidated the prior document revision, discarded
  1,023 staged UTF-16 units, and reconstructed the new document. Browser was
  re-observed and unchanged. A separate real Browser PageDown changed scroll
  0→282; independent recomputation found 1 scroll, 219 geometry and 90
  visibility changes while Notes stayed unchanged.
- Both scopes default to denial; separately granted Browser-only and Notes-only
  sessions were checked in addition to both-granted cases. Notes initial text
  denial, mid-range revoke, document protection and ancestor
  protection returned no restricted text. Fresh snapshots, a different role,
  and a fresh range could not bypass the restriction. Browser remained readable.
  Browser owner-side revoke denied new snapshots and the old node reference
  while Notes remained readable.
- Each Provider attempted reads and writes using the other source's active
  parent-held numeric pipe tokens: all four were denied and both sources were
  subsequently reread. After closure and creation of new pipes, four old
  parent tokens were denied. A same-boot restart produced new processes and
  rejected the old Browser instance. The diagnostic operation exists only in
  synthetic test builds; a numeric value is not an authorization grant.
- Separate actual guest cases covered normal exit of either Provider, a Notes
  exit during a range transaction, Browser exit while Notes is being read, a 30-second response timeout, a truncated
  response, source-epoch replacement, owner revocation and in-flight cooperative
  cancellation. The cancellation case discarded 1,023 staged units and the
  observed request-to-cancellation interval was 10 ms in that run, not a
  hard real-time guarantee. Source failures produced partial aggregates. In the
  cross-exit case, Browser pages had already passed their oracle, but Browser
  exited while Notes was staged; the final recheck omitted its old nodes and
  produced a partial aggregate with Notes complete.
- The guest Diff contract exercised 17 cases including source replacement,
  permission change, invalidation, unknown prior state, different scopes,
  incomplete geometry and malformed Notes length. `UNKNOWN` is not treated as
  `UNCHANGED`.

The display service admits a single exclusive Surface. For the baseline and
Browser-input cases, the real Notes process ran as a hidden, no-input session.
For real Notes input, Browser was a hidden, no-input process. The tests do not
establish two simultaneously visible windows or delivery of PS/2 input to a
background window. The ordinary `--notes-hidden` option is explicit and closes
that hidden session when its observation channel ends.

## Bounds and remaining limits

The exact contract is in [ssg_p3b_dual_source.md](../../contracts/ssg_p3b_dual_source.md).
There are two slots and one in-flight request per source; request/response
limits are 4,096/81,920 bytes, each operation is bounded to 30 seconds, and
separate 300-second request budgets prevent one source from consuming the
other's budget. Browser permits at most 4,096 nodes, 1 MiB of text and 1,024
pages; Notes admits at most 131,072 UTF-16 units, 512 ranges, three attempts
and 512 KiB of UTF-8. Exported aggregates are capped at 4 MiB. These are
bounded inputs and caches, not a measured hard peak-heap guarantee.

A cooperating caller can request source cancellation; the CLI has no
interactive cancellation control. No transparent provider restart/reconnect
is implemented. Random source instances are collision-resistant session
identifiers, not authentication or a mathematical guarantee across arbitrary
future boots. The platform has no exact global pipe-resource counter; the
four-pipe capacity and stale-token probes are narrower observations. No
physical hardware, SMP, arbitrary hostile applications or real-user data was
qualified. Browser evidence is limited to the static liteHTML fixture.

## Stress and affected guest regressions

All 48 complete synthetic sessions passed in one guest boot. Each independently reconstructed both streams, observed supervisor exit 0 and two uncancelled child exits 0, acquired four fresh pipes, rejected four old tokens, and returned to `free=130253, tasks=3, completions=1`. Observed shutdown times were 100–200 ms; complete-session wall times were 14.422–15.677 s. Browser diagnostic samples covered 7375 user pages and 4 threads; Notes samples covered 5404–5414 user pages and 2 threads. These are sampled values, not measured peaks; the four-pipe probe is not an exact global pipe counter. No session timed out. Individual results and serial captures are in the stress archive.

The affected guest and independent checks passed after one targeted retry. The first Notes boundary invocation failed before guest startup because a receipt input variable was missing; the unchanged probe then passed 13/13 in a fresh directory. The initial wrapper exit and failure log hash remain recorded. Browser covered full pagination with the independent structure oracle, real scroll Diff, interrupted-page recovery, retry-budget exhaustion, reload and cross-document reset/navigation. Notes covered the 3,623-UTF-16-unit read, 13 boundary checks, edit/no-edit, revoke, document/ancestor protection and ordinary no-raw-log behavior. The P1 suite exercised normal and fault paths, resource recovery and the xsh/dash entry points (17 checks); dash without spawn delegation was correctly denied. The dash ELF was the separately identified earlier build, rerun in this actual combination, not rebuilt here.

## Provenance and preserved failures

The guest image was reused read-only, not rebuilt by this branch: image SHA-256
`972f3a67012576022b67525da90c654a23b273b82cc0f1619fb6c529805ccd41`,
original system build ID `3cbbf35c826bb4bb`, original manifest SHA-256
`bf83ff680b6aeb043b1273ef9e1b7fd05dcff7b30ab94a4bf5fd5f675f50515`.

The environment was x86-64 QEMU 11.1.2 TCG, `pc-i440fx-10.0`, one CPU,
512 MiB and Qt 6.8.3; the host was arm64, Python 3.14.6, GCC/G++ 16.2.0 and
Binutils 2.47.20260726. QEMU executable SHA-256 was
`986c0aac646ff3a0d8bb6eeb2090813e0d3163bc9cff0388e78397ae6a206b7e`.
See the portable build receipts and per-case reports for executable/input hashes.

The first attempt had the second visible Qt process fail with display `-16`;
its partial aggregate is preserved. Another real edit hit Notes' unsaved-change
guard, after which the first harness timed out and cancelled that child; a
later run used the real Discard control and both children exited normally.
An initial Browser-denial verifier failed because the hidden owner digest had
not yet fired; the hidden test now emits it immediately while the visible
fixture retains its original single delayed diagnostic. The old single-source
exit timeout and diagnostic attempts are documented in PR #9's
`docs/reports/ssg_p3a2_notes_live_20261031/final-r2/failure-history.json`.
Its underlying race remains unresolved.

A later static review found that an earlier two-sample implementation lacked
its final Browser liveness recheck after reading Notes. No corresponding runtime
failure was claimed. Its stress run was deliberately stopped after 10 passing
sessions, and its raw summary still says `RUNNING`; the separate interruption
record identifies the operator stop. The corrected shared collection path was
rebuilt and the cross-exit scenario was tested on that build.

A subsequent scope review found the initial default granted both text scopes
without separate opt-in. The then-current stress run was deliberately stopped
after 19/48 passing sessions; its final summary says `PARTIAL`. Source and tests
were corrected before the final build; the 19 sessions are not counted toward
the corrected build’s stress result.

The first Notes boundary regression invocation failed before guest startup
because the regression wrapper had not required `XOS_BUILD_DIR`. Its raw log
hash is preserved. After requiring the SDK/Qt receipt inputs, the unchanged
13-check probe was rerun in a fresh directory and passed 13/13 with resource
restoration; the failed invocation is not relabeled as a pass.

The separate complete SDK license-material check did **not** pass: the reused
threaded SDK receipt lacks a `licenses` section, and a second attempt with the
reused system SDK found that `licenses/components.json` covers 24 components
while the current branch covers 32. Its SDK copy SHA-256 is
`9804a202c783eeb384b424bb4232e94687390a87c906be7821fbeadcaf6e81c8`,
compared with current source SHA-256
`a3aebd7c1aa208911b475a4cbd4f54e8a33f1bd09e3441821ebeb79edab497ca`.
A source-only check separately passed 175 registered source/notice/artifact
checks and SPDX presence for the 43 changed source files then in scope. A
separate marker-presence follow-up covered all 44 changed source files after
the regression wrapper was added. A later marker check covered all 45 changed
source files after the explicit-grant fix. This is not an exact SDK-copy or
archive-member legal audit, nor distribution qualification; no new dependency was added. Both failed attempts and the
source-only result are recorded in the failure history.

## Evidence and reproduction

- [Dual-source baseline](baseline.tar.gz), [ordinary two-sample run](ordinary-sample.tar.gz), and [ordinary three-program observation](ordinary-plain.tar.gz).
- [Default denial with captured IPC](default-denied.tar.gz), [ordinary default-denial observation](ordinary-default-denied.tar.gz), [Notes-only denial](notes-denied.tar.gz), and [Browser-only denial](browser-denied.tar.gz).
- [Notes edit](edit.tar.gz), [Browser scroll](browser-scroll.tar.gz), [Browser reload](browser-reload.tar.gz), and [source Diff contract](diff-contract.tar.gz).
- [Notes revoke](revoke.tar.gz), [document protection](protect-document.tar.gz), [ancestor protection](protect-ancestor.tar.gz), [Browser revoke](browser-revoke.tar.gz), and [cross-pipe isolation](pipe-isolation.tar.gz).
- [Browser exit during Notes read](browser-exit-during-notes.tar.gz), [Notes exit](notes-exit.tar.gz), [Browser exit](browser-exit.tar.gz), [timeout](notes-timeout.tar.gz), [truncated frame](notes-truncated.tar.gz), [cancellation](notes-cancel.tar.gz), and [same-boot restart](restart.tar.gz).
- [Repeated-session stress](stress.tar.gz), [suite results](suite-result.json), [guest-regression results](regression-result.json), and the [complete archive index](export-index.json).
- [Browser pagination/oracle regression](reg-pages-oracle.tar.gz), [Notes boundary regression retry](reg-notes-boundaries-retry.tar.gz), and [P1 pipe and shell regression](reg-p1.tar.gz).
- [Target build manifest](build-manifest.json), [test source provenance](test-source-provenance.json), [guest image provenance](image-provenance.json), [failure history](failure-history.json), [source-only license check](license-source-check.json), and [SPDX follow-up](spdx-followup.json).
- [Export scan](export-scan-result.json), [archive and independent-replay checks](export-replay-result.json), and the preserved interrupted-run summaries ([earlier](interrupted-v12-raw-summary.json), [later](interrupted-v13-raw-summary.json)).
- [Staged-index scan before adding its receipt](index-scan-pre-receipt.json) and [proposed PR-body scan](pr-body-scan.json). The complete index was scanned again after adding these receipts and updating the checksum file.

Each evidence archive has an `export-manifest.json` listing original local
member SHA-256, exported member SHA-256 and any portable-JSON transformation.
Raw host logs remain local. Synthetic serial captures and exact received IPC
payloads are preserved; test frame headers can be reconstructed from their
recorded protocol fields. The export scanner also inspects decoded frame and
oracle payloads, archive member names and metadata. See `export-index.json` and
`SHA256SUMS` for the exported artifacts. No private absolute path is required.

Configure the named environment variables for a matched XOS image, SDK, Qt
build/source, host Qt tools, binutils and QEMU. Use a new directory inside the
repository's `build/`; no command below overwrites prior evidence.

```sh
export XOS_ROOT="$(git rev-parse --show-toplevel)"
export QEMU="$XOS_QEMU"
python3 "$XOS_ROOT/scripts/build_ssg_p3b.py" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --qt-source "$XOS_QT_SOURCE" --host-qt "$XOS_HOST_QT" \
  --binutils "$XOS_BINUTILS" --output "$XOS_ROOT/build/p3b-repro"
export XOS_P3B_BUILD_DIR="$XOS_ROOT/build/p3b-repro"
python3 "$XOS_ROOT/tests/ssg_p3b_guest.py" --image "$XOS_IMAGE" \
  --supervisor "$XOS_P3B_BUILD_DIR/aggregate-test/ssg-multi.elf" \
  --browser "$XOS_P3B_BUILD_DIR/browser-test/browser.elf" \
  --notes "$XOS_P3B_BUILD_DIR/notes-test/notes.elf" \
  --input "$XOS_ROOT/tests/fixtures/ssg_browser/p2f.html" \
  --output "$XOS_ROOT/build/p3b-repro-baseline"
python3 "$XOS_ROOT/tests/ssg_p3b_verify.py" \
  "$XOS_ROOT/build/p3b-repro-baseline" \
  --browser-receipt "$XOS_P3B_BUILD_DIR/browser-test/browser.portable.receipt.json"
python3 "$XOS_ROOT/tests/ssg_p3b_stress_guest.py" --image "$XOS_IMAGE" \
  --supervisor "$XOS_P3B_BUILD_DIR/aggregate-test/ssg-multi.elf" \
  --browser "$XOS_P3B_BUILD_DIR/browser-test/browser.elf" \
  --notes "$XOS_P3B_BUILD_DIR/notes-test/notes.elf" \
  --input "$XOS_ROOT/tests/fixtures/ssg_browser/p2f.html" \
  --browser-receipt "$XOS_P3B_BUILD_DIR/browser-test/browser.portable.receipt.json" \
  --count 48 --output "$XOS_ROOT/build/p3b-repro-stress"
```

Use the same guest command with `--case edit`, `revoke`, `protect-document`,
`protect-ancestor`, `browser-revoke`, `browser-reload`, `browser-scroll`,
`pipe-isolation`, `notes-exit`, `browser-exit`, `browser-exit-during-notes`, `notes-timeout`,
`notes-truncated` or `notes-cancel` and a new output directory. Run the matching
`tests/ssg_p3b_*_verify.py` checker; see the case archives for the exact test
input and events. `tests/ssg_p3b_restart_guest.py` checks two sessions within
one boot. The guest runner normally opts in to both synthetic text scopes;
use `--default-denied` with the diagnostic builds, or
`--ordinary-default-denied` with all three ordinary builds, and verify with
`tests/ssg_p3b_default_denied_verify.py` to exercise refusal with no grants.
To rerun the affected Browser, Notes and P1 guest regressions using the same
build, retain the matching `XOS_SDK_PREFIX`, `XOS_BUILD_DIR` and `XOS_QT_SOURCE`
settings, set `XOS_DASH_ELF` to a separately built dash ELF, and run:

```sh
export XOS_DASH_ELF="${XOS_DASH_ELF:?Set XOS_DASH_ELF to the separately built dash ELF}"
bash "$XOS_ROOT/scripts/run_ssg_p3b_regressions.sh" \
  "$XOS_P3B_BUILD_DIR" "$XOS_ROOT/build/p3b-repro-reg"
```

The wrapper runs all cases even if one fails, records each exit code, and
returns nonzero if any step fails. Each output prefix must be fresh.

Before public delivery, scan the actual Git index and the proposed PR body:

```sh
python3 "$XOS_ROOT/tests/check_public_evidence_paths.py" --index \
  --base "$XOS_PR_BASE" --deny-identity "$XOS_PRIVATE_IDENTITY"
```

At the time of review, GitHub reported no checks for this draft branch; no CI
pass is claimed. Issue #37 remains open and historical objects may still
contain older path material. This branch does not rewrite history, force-push,
or close that issue.
