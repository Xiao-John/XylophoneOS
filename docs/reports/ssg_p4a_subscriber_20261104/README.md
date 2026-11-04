# XylophoneOS SSG-P4A read-only subscription

2026-11-04 · `SSG_P4A_READ_ONLY_SUBSCRIPTION=PASSED_SCOPED`

This report records a real XOS/QEMU userland subscription session based on
upstream `main` at `6fe330ce2dd9441d72da611c1f87b80dad8e3b03`. Browser and Notes
were launched as separate Providers by a trusted userland Supervisor. A fourth
process, the independent Subscriber, received source events over a dedicated
Pipe and returned a separate ACK Pipe. No kernel, syscall, system ABI, driver,
QPA, or scheduler changes were made.

## Acceptance matrix

| Gate | Result | Scope |
|---|---|---|
| `P4A_EVENT_SINK_ABSTRACTION` | `PASSED` | P3C Console Sink preserved; bounded Pipe Sink added |
| `P4A_REAL_GUEST_SUBSCRIPTION` | `PASSED_SCOPED` | Four independent guest processes; Browser and Notes initial baselines, sequence checks and ACKs |
| `P4A_SUBSCRIBER_STATE` | `PASSED_SCOPED` | 25 Guest checks for state continuity, identity, epochs, revocation, protection, invalidation and frame parsing |
| `P4A_EVENT_ACKNOWLEDGEMENT` | `PASSED_SCOPED` | Matching ACK after in-memory validation; wrong and duplicate ACKs stop delivery as `UNKNOWN` |
| `P4A_BACKPRESSURE` | `PASSED_SCOPED` | 4,096-byte frame fills the actual Pipe; next atomic byte returns `WOULD_BLOCK`; ACK deadline yields `UNKNOWN` without replay |
| `P4A_NOTES_EDIT` | `PASSED_SCOPED` | Two PS/2 edits change Notes revision; Browser stays `UNCHANGED` |
| `P4A_BROWSER_SCROLL` | `PASSED_SCOPED` | Two PS/2 scrolls change Browser summary; Notes stays `UNCHANGED` |
| `P4A_PERMISSION_REVOCATION` | `PASSED_SCOPED` | Notes revocation, document protection and ancestor protection clear current summaries; Browser remains independent |
| `P4A_SOURCE_FAILURE` | `PASSED_SCOPED` | Browser and Notes exits each become `UNAVAILABLE`; the other source continues |
| `P4A_RESYNC` | `PASSED_SCOPED` | Corrupt or uncertain delivery is not replayed; a new session receives new source instances and fresh baselines |
| `P4A_GUEST_STRESS` | `PASSED_SCOPED` | 12/12 complete first-subscription runs |
| `P4A_P3C_COMPATIBILITY` | `PASS` | P3C contract probe and ordinary three-cycle Console Watch both rerun |
| `P4A_PUBLIC_EVIDENCE_SCAN` | `PASS` | Flat manifest, public-path, source, SPDX and documentation checks |
| `P4A_PRODUCTION_BROKER` | `NOT_IMPLEMENTED` | This remains an explicitly prewired prototype |
| `P4A_LOCALPILOT_END_TO_END` | `NOT_RUN` | No production LocalPilot or Permission Gateway integration |

P3C's sequential observation model remains unchanged: `globalAtomicSnapshot =
NOT_IMPLEMENTED`. The ACK proves only that the Subscriber validated and updated
its in-memory read-only source state; it proves no application action.

## Transport and resource evidence

The implementation uses a 28-byte little-endian header (`SGEV` events,
`SGAK` ACKs), version 1, a per-stream sequence, source slot, payload length and
an FNV-1a corruption check. The check is not authentication. Event payloads fit
within the 4,096-byte Pipe; the normal summary limit is 512 bytes. The
Supervisor waits for the matching ACK before sending another event, so only
one event can be unconfirmed. After an ACK timeout or mismatch it stops and
requires a new session baseline; it never automatically replays.

Each normal P4A run used six Pipe objects. The measured available-object sample
was 8 before and 8 after each session; the existing four-object reuse probe
acquired 4/4 and rejected all four closed source tokens. The kernel has no
exact global Pipe counter, so the report claims only these bounded observations.
Global process/free-page samples returned to their pre-session values. While a
Supervisor was alive, its allocator retained a 9–73 page per-process high-water
delta depending on the scenario; the process exited and those pages returned to
the system afterward. The 12 repeated first-subscription runs each had two
events, two matching ACKs, no timeout/unknown result, clean child exits, and
restored resource samples.

The synthetic full-Pipe case observed the Subscriber commit a frame after the
Supervisor's ACK deadline, then fail its ACK write because the parent had
closed the read end. The Supervisor recorded `UNKNOWN`, sent no second event,
and exited unsuccessfully for that injected fault. A later session used new
source instances and new initial baselines. The protocol does not claim
transparent recovery.

## Preserved iteration record

The initial full validation output is retained as `validation_initial_attempt.json`.
Its duplicate-ACK Guest check expected the Subscriber to fail writing the next
ACK. The guest instead showed that the ACK write succeeded into the Pipe while
the Supervisor correctly rejected the duplicate prior sequence. The test was
corrected to accept that valid outcome and the duplicate-ACK scenario passed in
the complete rerun recorded by `validation_summary.json`; the initial failed
attempt remains in the report. Earlier bring-up issues and their fixes are
summarized in `test_iteration_notes.json`.

## Boundaries

The topology trusts its prewired parent and source-instance consistency values;
neither values nor frame checksums authenticate a peer or grant permission.
There is no dynamic discovery, production broker, action execution, model
instruction channel, replay queue, remote revocation service, multiwindow input,
or production Permission Gateway. `EXIT_RACE_ROOT_CAUSE=UNRESOLVED` remains
unchanged. The report's root `manifest.json` covers every file in this directory
and no other file hashes itself or a sibling.
