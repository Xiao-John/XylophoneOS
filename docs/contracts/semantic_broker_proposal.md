# XOS Semantic Broker — design and transport feasibility

2026-10-30. **PROPOSED / NOT IMPLEMENTED / NOT APPROVED.** The broker, permission
service, discovery, subscriptions and action routing described here are user-space
services. This text allocates no syscall, endpoint, wire opcode or public ABI.
Application-local Qt/Browser scene snapshots are not cross-process authority.

## Actual transport evidence and its limits

On base `3377dbf`, the real guest probe in
`docs/reports/semantic_broker_pipe_20261030/` starts an ordinary parent with
explicit child-spawn delegation. It creates two existing 4096-byte pipes, wires
its not-yet-started child to one input and one output, and exchanges a bounded
synthetic request/reply. Twelve checks cover successful transfer, closed ends,
queue-full backpressure, drain, broken reader, stale local reference, child exit
and EOF. Attempting to rewire the running child returns `process_error_state`.
The same test launched as a dash child without delegated child-spawn rights
fails with `-1`, as intended. Resource counters return to baseline.

This is a real, restricted **parent/child pipe topology**, and it is more precise
than saying all cross-process communication is unavailable. The payload is a
synthetic 16-byte message, not a Qt/Browser SSG snapshot or an authorized action.
The probe does not test dynamic discovery, hostile peers, multiple clients,
subscriptions, reconnect, cancellation or production authorization.

Source inspection shows that the current APIs wire a parent's pipe reference to
an owned child while that child is being built; they do not establish an arbitrary
new channel to an already-running unrelated app. Ordinary pipes are byte streams:
they do not authenticate a sender per message, and a reference can have multiple
holders (including through permitted process inheritance). Closing one's own end
does not revoke every other holder. The current pipe wait is for one pipe and
does not take an absolute deadline; no generic wait-any/peer-discovery contract
is established here. Current limits include eight system pipe objects, 4096 bytes
per pipe and up to 16 pipe references per process. Writes can be short or return
would-block; the atomic flag has a bounded maximum. These constraints require
framing, admission control and measured resource budgets, not file-service
identity reuse or serial/global-file transport.

The next experiment may connect a cooperating provider launched by a trusted
session parent to a one-client consumer using these inherited routes, while
clearly marking the topology and missing guarantees. It cannot discover arbitrary
running apps or serve as a production session-wide broker. A separate generic
mechanism review must determine whether authenticated dynamic peer establishment,
rights attenuation, disconnect/revocation and deadline/multi-source waiting can
be provided by existing primitives or need a general mechanism. No SSG-specific
syscall or preselected ABI is proposed.

## Participants and reference identity

The session authority manages service instances and user decisions; an application
provider owns its local semantic data; the broker filters and routes only within
delegated rights; a consumer such as LocalPilot proposes queries/actions. A
production source identity must bind a kernel-authenticated connection to a fresh
service/process instance and user-session epoch. Self-reported names, PIDs and
object IDs do not authenticate a provider. A node reference includes source
instance/epoch, node ID and expected node or scene version. On provider restart,
navigation, destruction, revocation or epoch replacement, stale references must
be rejected rather than referring to later objects. A process-local PID+counter
is not sufficient across PID reuse, reboot or independent service lifetimes.

## Proposed operations (symbolic, no wire numbers)

| Operation | Bounded behavior and authority |
|---|---|
| Enumerate authorized roots | Return only app/window roots permitted to this consumer; discovery is not observation authority |
| Snapshot/query | Filter by role/text/state/visibility with explicit query scope, node/text/byte/depth/time limits, completeness and observation time |
| Details/document range | Recheck scope and sensitivity for the exact live reference; document presence does not mean text is on screen |
| Subscribe | Deliver bounded versioned changes; signal overflow/gap and require snapshot resync. No unbounded queues or silent loss |
| Propose action | Carry source and node epochs, expected state/version, typed operation and bounded parameters; no side effect and no lease creation |
| Authorize and execute | Trusted permission service approves exact subject/target/action/sensitivity/purpose/expiry; provider revalidates the live target and lease immediately before dispatch |
| Receipt/verify | Bind request and source generation; distinguish verified result, refused, failed and `UNKNOWN`. Reconcile UNKNOWN without automatic replay |

Snapshot/diff removal means a node left the specified result, not necessarily
that the underlying object was destroyed. Capped or scope-changed snapshots cannot
prove complete removal. Global screen geometry/occlusion remains unknown until a
qualified compositor provides it. The compositor's rendering access and an AI
consumer's semantic observation or action authority remain distinct.

## Consent, policy and failure

User-granted scope may cover a selected object, application, workspace or the
user session, but must name the consumer, operations, sensitivity, duration and
revocation rules. Passwords and protected material need explicit stricter policy;
cross-origin frame access is decided by the browser's trusted origin boundary.
Discovery, models, app-provided text and untrusted descriptors cannot grant,
broaden or renew rights. Each operation checks current policy, expiry and source
generation; a stale receipt or cached snapshot must not resurrect revoked access.

Resources are admitted before allocation: bounded messages, text, nodes,
snapshots, provider count, per-client queue and subscription count. Define
backpressure and cancellation without claiming an unacknowledged action failed.
Disconnect invalidates grants and pending references; a lost response is UNKNOWN
if dispatch may already have occurred. Restart creates a new authenticated epoch,
and reconnection must reauthorize instead of silently reviving old rights.
Deadlines use the system monotonic domain under C29; an observation timestamp,
media position or wall clock cannot substitute for that deadline.

## Required next gates

Review generic channel establishment and revocation separately; then test an
actual provider and consumer with least privilege, bounded frames/queues, denial,
truncation, stale IDs, service death, cancel and reconnect under both applicable
shells. Further gates cover workspace consent, cross-origin policy, independently
observable action results, hostile providers, accessibility, multiwindow geometry
and long stress. None is established by this probe.
