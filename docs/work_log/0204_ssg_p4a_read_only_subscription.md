# 0204 — SSG P4A read-only subscription

2026-11-04 · Branch `codex/ssg_p4a_subscriber_20261104` · base
`6fe330ce2dd9441d72da611c1f87b80dad8e3b03` (freshly fetched upstream main).

During the long validation, upstream main advanced to
`071330f3b196d357c4a823f1719793b449513b86`. The PR branch now merges that
release-preparation delta; inspection found no kernel, shared ABI, or
user-runtime source changes in the delta. The full matrix remains bound to its
`6fe330c` system image, and an additional first-subscription QEMU smoke passed
on the post-sync system image (`f8eb0815098ae436`).

## Scope and result

Implemented the next userland slice after P3C: a separate read-only XOS
Subscriber receives Browser and Notes source events over a dedicated Pipe and
returns bounded acknowledgements on a second dedicated Pipe. The final result
is `SSG_P4A_READ_ONLY_SUBSCRIPTION=PASSED_SCOPED` for the synthetic QEMU
scenarios in [`docs/reports/ssg_p4a_subscriber_20261104/`](../reports/ssg_p4a_subscriber_20261104/).

The current `main` sources contain P3B/P3C even though the global `docs/state.md`
snapshot lags its merge records. The actual commit, source, contracts and new
guest evidence were used; `docs/state.md` was not modified, as required. The
later C30 rename had left P3C references using `ssg_pipe::Baseline` and
`ssg_pipe::Diff`; these now use `ssg_pipe::baseline` and
`ssg_pipe::baseline_diff_result` so the affected Watch target builds against
the current main.

## Implementation

- Added an `event_sink` abstraction with a compatible P3C Console sink and a
  P4A Pipe sink. P3C's console frames are still emitted only in the console
  mode; the new Subscriber never decodes serial output.
- Added `src/user/apps/ssg_subscriber.cpp` as a real independent process. It
  checks version, frame length, checksum, source slot, expected prewired source
  instance, stream sequence, source-local sequence, epoch and revision
  continuity. It holds source-level state and bounded summaries only; it does
  not reconstruct a DOM or retain Notes text.
- Added private `SGEV`/`SGAK` framing: a 28-byte little-endian header, protocol
  version 1, stream sequence, payload length, source slot and a bounded
  FNV-1a corruption check. FNV-1a is not authentication. Maximum event payload
  is 4,068 bytes, keeping the complete event within one existing 4,096-byte
  Pipe write; summaries are capped at 512 JSON bytes and sixteen fields.
- The trusted Supervisor passes Subscriber fd 0 as the event Pipe reader and
  fd 1 as the ACK Pipe writer; stderr remains the diagnostic console. The
  Subscriber receives no Provider token. Qt startup diagnostics no longer
  share the ACK route.
- The Supervisor sends one event and waits for the exact ACK before sending
  another. Pipe writes are atomic and bounded; ACK waits use the existing
  monotonic `sys_pipe_wait` deadline. Wrong, duplicate, late, missing, or lost
  ACKs stop the stream as `UNKNOWN` or `REJECTED`, require a new baseline, and
  are never replayed. ACK proves an in-memory Subscriber update only; it does
  not prove an external action.
- Added isolated current-main SDK/Qt overlay preparation because the cached Qt
  E17 SDK still exported `file::Client` while current main exports
  `file::client`. The local overlay uses the current-main header and object and
  leaves the separate Qt build untouched.
- No kernel, syscall, public ABI, QPA, display service, driver, scheduler,
  clock, IRQ or LocalPilot source/configuration was changed.

## Resources and acceptance evidence

Current main defines eight Pipe objects, 4,096 bytes per Pipe and sixteen Pipe
references per process. A normal P4A session uses six Pipe objects: four for
Browser/Notes request-response and two for Subscriber events/ACKs. The full
Pipe QEMU case filled one Pipe with a 4,096-byte event, observed the next
atomic-byte probe return `WOULD_BLOCK`, crossed the ACK deadline, and reported
`UNKNOWN` without a second event. The Subscriber committed in memory after
that timeout, then its ACK write failed because the Supervisor closed the ACK
reader. A new session used fresh source instances and new initial baselines.

The final full validation is recorded in `validation_summary.json`. It ran
14 source/delivery scenarios plus two resynchronization sessions and 12
complete first-subscription stress sessions, in sequence. The 12 stress runs
all passed: two events/two ACKs, no timeout or unknown delivery, clean exits,
resource counters restored. A separate Guest state test passed 25 checks; the
host reference protocol model passed 30 checks. P3C's 32-check contract guest
and an ordinary three-cycle stdout Watch run passed after the Event Sink
refactor.

| Gate | Result |
|---|---|
| `P4A_EVENT_SINK_ABSTRACTION` | `PASSED` |
| `P4A_REAL_GUEST_SUBSCRIPTION` | `PASSED_SCOPED` |
| `P4A_SUBSCRIBER_STATE` | `PASSED_SCOPED` — 25 Guest checks |
| `P4A_EVENT_ACKNOWLEDGEMENT` | `PASSED_SCOPED` — matching, wrong, duplicate, rejected and lost ACK cases |
| `P4A_BACKPRESSURE` | `PASSED_SCOPED` |
| `P4A_NOTES_EDIT` | `PASSED_SCOPED` |
| `P4A_BROWSER_SCROLL` | `PASSED_SCOPED` |
| `P4A_PERMISSION_REVOCATION` | `PASSED_SCOPED` — DENIED, document protection and ancestor protection |
| `P4A_SOURCE_FAILURE` | `PASSED_SCOPED` — Browser and Notes exit independently |
| `P4A_RESYNC` | `PASSED_SCOPED` — new instances and fresh baselines, no replay |
| `P4A_GUEST_STRESS` | `PASSED_SCOPED` — 12/12 |
| `P4A_P3C_COMPATIBILITY` | `PASS` |
| `P4A_PUBLIC_EVIDENCE_SCAN` | `FAIL` — P4A manifest, public-path, source, C30 and SPDX checks pass; repo-wide `docs_consistency` finds two links to an absent upstream `docs/releases/playbook.md` |
| `P4A_PRODUCTION_BROKER` | `NOT_IMPLEMENTED` |
| `P4A_LOCALPILOT_END_TO_END` | `NOT_RUN` |

The bounded available-Pipe sample was 8 before and 8 after the P4A session;
the four-object reuse probe acquired 4/4 and all four closed Provider tokens
were denied. This is a capacity/reuse observation, not an exact global Pipe
counter. Global free-page/task/completion samples returned to baseline after
the Supervisor exited. While it was alive, the Supervisor allocator retained a
9–73 page per-process high-water delta depending on scenario; those pages were
reclaimed at process exit. The native-thread exit race root cause remains
`UNRESOLVED`.

## Preserved failed attempts and limitations

The earlier `p4a-validation-final-01` summary is retained. Its duplicate-ACK
test assertion required the Subscriber's next ACK write to fail. The guest
instead showed that the write succeeded into the Pipe while the Supervisor
correctly rejected the stale ACK sequence and stopped as `UNKNOWN`. The test
now accepts either a successful local write or a broken ACK Pipe; the corrected
duplicate-ACK scenario and final 12-run suite both passed. Other bring-up
iterations and their corrections are listed in `test_iteration_notes.json`;
none of those failure records were deleted.

After C30-lowercasing a local verifier constant, a post-sync audit initially
raised a Python variable-shadowing exception despite the Guest pass. The
decoded header field was renamed, and the corrected independent verifier was
run over all saved scenarios, resync records, and stress logs; all passed.

The repo-wide `docs_consistency` run on merged upstream `071330f3` fails on
two links from `docs/releases/next_release.md` to the absent
`docs/releases/playbook.md`. The referenced file is absent from upstream
`main`; the P4A branch leaves that unrelated release documentation unchanged.
The P4A flat manifest, public-path, C30 and SPDX checks pass.

The prototype is one-client and explicitly prewired. It provides no
application discovery, peer authentication, durable replay, transparent
reconnect, in-session Provider restart, multiwindow input, permission gateway,
action execution, or model integration. Source-instance values are
consistency identifiers, not credentials. Notes/Browser samples are
sequential; `globalAtomicSnapshot=NOT_IMPLEMENTED`.

Reproduction templates and tool versions are in `p4a_build_manifest.json` and
`system_build_summary.json`; detailed QEMU input, TX/RX frame captures,
ACKs, exit records and 12 stress logs are covered by the report's flat root
`manifest.json`.
