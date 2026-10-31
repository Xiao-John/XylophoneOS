# SSG P3B: two explicitly wired sources

This is a bounded, read-only user-space prototype. It is not a production broker,
application discovery service, cross-process action interface, or desktop-wide
permission system. The supervisor must already have authority to start children.
It creates a separate request pipe and response pipe for each source, transfers
only that source's provider ends at spawn, and retains the opposite ends itself.
One request per source can be in flight; there is no unbounded request queue.
The source slot is assigned by this wiring, not by a document, request, model, or
provider-supplied type. The child PID and source fields are consistency checks,
not grants or authentication. Text access is denied by default for each source;
the trusted caller must opt in independently using `--browser-text` and
`--notes-text`, subject to the application owner's decision. An explicit
`--browser-denied` or `--notes-denied` overrides the corresponding grant.
Neither source receives the other's pipe ends.

The current display service admits one exclusive Surface. An explicitly requested
`--notes-hidden` session runs the actual Notes document and widget tree without a
Surface or input route, and ends that hidden session when the observation pipe
ends. The separately compiled synthetic test Browser can instead be hidden so
Notes receives real keyboard input. A hidden source is not a visible window and
cannot receive background PS/2 events. The `presentation` field states this scope.
No QPA, kernel, system ABI, driver, scheduler, or global permission changes are
part of this contract.

## Aggregate observation

The output is one finite observation, not a continuously refreshed desktop view.
A source is sampled over its own monotonic start/end interval. The Browser and
Notes intervals are sequential; `globalAtomicSnapshot` is `NOT_IMPLEMENTED`.
Each completed source explicitly says `UNVERIFIED_AFTER_OBSERVATION`; a failed
source says `NOT_CURRENT`. Neither is a live freshness guarantee.
`AGGREGATE_COMPLETE_OBSERVED` means both sources completed their individual
bounded observations. It does not mean the sources were simultaneously current
at one instant. If a source fails, is unavailable, denied, or protected, the
aggregate is `AGGREGATE_PARTIAL` and that source does not contain a fabricated
complete document or node set. A later sample must actually re-observe a source;
the prototype does not certify a cached historical source as current.
For a two-source sample, the supervisor rechecks both child processes after
both reads and suppresses a source that has already exited. This is a bounded
liveness observation, not an atomic snapshot or a promise that a child cannot
exit immediately afterward.

Each Browser node has an identity object containing `slot`, `sourceInstance`,
`sourceEpoch`, and `localNodeId`. Its `parent` is a local node ID interpreted only
inside that same source and epoch. Notes uses the same compound identity for its
document node. The trusted parent generates separate random source instances;
if randomness fails or the two instances collide, the session fails closed.
Browser also records its revision and pagination session; Notes records its
UTF-16 document revision. An epoch or instance change invalidates old references;
restarting and reconnection are not implemented as transparent recovery.
Browser data includes the observed scroll position and bounded local geometry;
these do not establish compositor occlusion or global visibility. Browser
completeness is locally validated traversal and still needs an independent
oracle for the tested document; Notes completeness is a revision-consistent
transaction and still needs an owner reference for independent qualification.
Per-node fragment completeness is retained separately.

The Browser adapter uses `snapshot_begin` / `snapshot_next`, cursors and the
existing `BaselineCollector`. The Notes adapter uses a document snapshot followed
by `text_range` requests, preserving UTF-16 offsets and one document revision.
A reset, denial, protection, malformed response, timeout or resource failure
invalidates the in-progress Notes transaction; it cannot publish a mixture of
versions. A previously delivered authorized observation cannot be retroactively
undisclosed, but it is not republished as the current restricted document.

The normal supervisor logs status and lifecycle records only. Its explicit
`--emit-aggregate` option emits the full aggregate, including authorized text,
to its diagnostic console. Raw IPC frame capture and owner-control shortcuts are
compiled only into the synthetic test executables. Do not enable such diagnostics
for real user material. The synthetic isolation probe passes numeric token
values to each test Provider and checks that the kernel denies access to the
other source's parent-held endpoints; numbers are not transferred handles. The
ordinary Provider does not include this diagnostic operation.

An ordinary session may request `--sample-twice` with a bounded
`--sample-interval` of 1–30 seconds. The second observation is collected again
from both sources rather than promoting the first sample to current state. Its
source-scoped Diff distinguishes `CHANGED`, `UNCHANGED`, `REPLACED`,
`INVALIDATED`, `PERMISSION_CHANGED`, and `UNKNOWN`; it does not compare nodes
using a desktop-wide numeric ID. Observation timestamps and Browser pagination
session IDs are not by themselves content changes. The result remains a
comparison of sequential per-source observations, not an atomic desktop event.
Changing observation scope or presentation yields `UNKNOWN`. Browser samples
with incomplete fragment geometry also yield `UNKNOWN`; an unavailable earlier
sample cannot by itself establish that a later refusal is a permission change.

## Bounds and lifecycle

- At most two provider slots, each with one in-flight request.
- A request is at most 4,096 bytes and a response at most 81,920 bytes.
- Each transfer has a 30-second monotonic deadline; each source client has a
  separate 300-second budget charged while its own requests execute. Time spent
  reading the other source does not consume that budget. A terminal transport
  error is not retried forever.
- A cooperating caller can atomically cancel a client. The transfer loop checks
  cancellation between nonblocking operations and its bounded sleeps; its
  controller must then close the affected session routes. The command-line
  prototype does not provide an interactive cancellation control. A request
  already committed before cancellation is not retroactively undone.
- Browser collection retains at most 4,096 nodes, 4 MiB of collected node data,
  1 MiB of node text and 1,024 pages. Notes admits at most 131,072 UTF-16 units,
  512 ranges, three attempts and 512 KiB of encoded text. An exported aggregate
  is capped at 4 MiB; its combined content is bounded by 4,097 source nodes and
  1.5 MiB of Browser/Notes text. Two simultaneous committed Browser baselines
  occur only during an explicitly requested bounded two-sample comparison.
- Parent-owned pipe tokens are closed on session completion. Child exit is
  polled with a bound; the fallback cancels a still-running child and reports
  that outcome. A cancelled child or failed reap makes the supervisor fail.
  The pipe-capacity probe in tests is not an exact system-wide pipe counter.
  Test sessions also attempt the closed parent tokens after creating new pipes;
  these checks are scoped to the existing token implementation and tested boot.

The prior single-source Consumer's watchdog now uses a joinable native worker;
that change is retained from the Notes branch. Previous intermittent exit hangs
and their diagnostic history are not proof of a resolved root cause. Individual
stress runs can establish only the behavior observed for their actual build and
inputs.
