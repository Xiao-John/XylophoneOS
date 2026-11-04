# SSG P4A: prewired read-only subscription prototype

2026-11-04. Status: `SSG_P4A_READ_ONLY_SUBSCRIPTION=PASSED_SCOPED` for the
synthetic Browser/Notes guest sessions and the listed QEMU inputs. This extends
P3C's bounded source observer with a dedicated event Pipe, an independent
read-only Subscriber process, and one-event-at-a-time acknowledgements. It is
not a production broker or an OS authorization boundary.

## Process and Pipe topology

The trusted session supervisor starts Browser, Notes, and Subscriber as
independent user processes. It creates the existing request and response Pipe
for each provider, plus one event Pipe and one ACK Pipe:

| Pipe | Supervisor holds | Provider/Subscriber receives |
|---|---|---|
| Browser request | write end | Browser read end at fd 0 |
| Browser response | read end | Browser write end at fd 2 |
| Notes request | write end | Notes read end at fd 0 |
| Notes response | read end | Notes write end at fd 2 |
| Subscriber events | write end | Subscriber read end at fd 0 |
| Subscriber ACKs | read end | Subscriber write end at fd 1 |

The Subscriber receives no Browser or Notes Pipe token. Its stderr (fd 2)
remains on the diagnostic console; the event and ACK routes are dedicated
Pipe-backed standard routes. The Subscriber does not create a Qt application
object or write diagnostics on fd 1, because Qt startup diagnostics on stderr
would corrupt a stderr-backed ACK channel. Test-only frame captures use the
console and are never the transport.

The current kernel provides at most eight Pipe objects, 4,096 bytes per Pipe,
and at most sixteen Pipe references per process. A normal P4A session uses six
Pipe objects: four for the two request/response providers and two for the
subscription. The supervisor holds six references; each child receives two
references. These are existing userland Pipe and spawn mechanisms; this change
adds no syscall, kernel code, or public ABI.

`sys_pipe_wait` waits on one route and accepts an absolute monotonic deadline.
The supervisor and Subscriber use five-second transfer deadlines. Read and
write calls are retried only after a matching readiness result. Event frames
are written with the existing atomic Pipe flag, so the kernel accepts either
the whole bounded frame or no bytes. A partial result is still treated as
unknown and ends the stream.

## Event frame and source state

The private, versioned framing is distinct from P1 request/response frames:

| Offset | Field |
|---:|---|
| 0 | `SGEV` for an event or `SGAK` for an ACK |
| 4 | little-endian protocol version (`1`) |
| 6 | header size (`28`) |
| 8 | frame kind (`1` event, `2` ACK) |
| 10 | reserved flags (`0`) |
| 12 | stream sequence |
| 16 | payload byte length |
| 20 | FNV-1a payload check value |
| 24 | source slot (`1` Browser, `2` Notes; `0` ACK) |
| 26 | reserved (`0`) |

The maximum event payload is 4,068 bytes so the complete frame fits in one
4,096-byte Pipe write. P4A keeps the source-scoped P3C event JSON: source slot,
trusted prewiring instance, provider epoch, source-local sequence, revision
before/after, observation scope, capability summary, event type,
completeness, freshness, failure reason, and a bounded summary. The producer
and Subscriber each limit summaries to sixteen fields and 512 compact JSON
bytes. No DOM nodes or full Notes text are sent to the Subscriber. FNV-1a is
only accidental-corruption detection; it is not cryptographic authentication.

The ACK has a four-byte little-endian status (`1` committed in memory, `2`
rejected) and the exact stream sequence. It acknowledges the Subscriber's
validated in-memory read-only source state only. It does not certify that an
application action ran or that any external state changed.

The Subscriber keeps separate Browser and Notes records: expected source
instance, epoch, revision, scope, source-local sequence, source state,
completeness, freshness, last failure, and last valid bounded summary. It never
uses event text as instructions or authority. It accepts a changed/unchanged
event only with a contiguous baseline, matching source instance/epoch, and
matching prior revision. Denial, protection, unavailability, epoch replacement,
malformed frames, invalid ordering, and missing continuity clear or invalidate
the current summary. Browser and Notes state cannot update one another.

## Delivery, failure, and resynchronization

The supervisor sends an event, waits for the Subscriber to read and validate
it, then waits for the matching ACK before sending another event. There is at
most one unconfirmed event. The test-only full-Pipe scenario writes an exactly
4,096-byte event frame, observes a subsequent atomic byte probe return
`WOULD_BLOCK`, and pauses the Subscriber beyond the ACK deadline. The
supervisor stops without retry and marks delivery `UNKNOWN`; the Subscriber
may have committed the frame before its ACK write fails. This is intentionally
not interpreted as a successful ACK or as an event that is safe to replay.

Malformed/checksum-invalid input receives a bounded rejection ACK if its
sequence can be read. A wrong, duplicate, or late ACK, a timeout after sending,
or a lost ACK is `UNKNOWN`; the watch ends and requires a new session baseline.
There is no replay queue, durable offset, transparent resume, or in-session
provider restart. A later trusted supervisor run assigns fresh source-instance
values and observes new Browser and Notes baselines. The values are collision
resistant consistency identifiers, not credentials, peer authentication, or
permission grants. Provider-provided JSON IDs are not used to authorize access.

The session's Browser and Notes observations are sequential; they do not form
an atomic desktop snapshot. `globalAtomicSnapshot=NOT_IMPLEMENTED`. A provider
exit yields `UNAVAILABLE` for that source while the other slot continues. The
prototype does not restart providers inside the session.

## Boundary and non-goals

Observation is explicitly prewired and read-only. The prototype adds no
arbitrary application discovery, permission gateway, action transport, GUI
input, file modification, or model integration. Action Proposal is not
Authorization. `P4A_PRODUCTION_BROKER=NOT_IMPLEMENTED` and
`P4A_LOCALPILOT_END_TO_END=NOT_RUN`. The historical native-thread exit race
remains `EXIT_RACE_ROOT_CAUSE=UNRESOLVED`. See the run matrix and evidence in
[`docs/reports/ssg_p4a_subscriber_20261104/`](../reports/ssg_p4a_subscriber_20261104/).
