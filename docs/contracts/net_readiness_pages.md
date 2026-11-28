# Net2 immediate readiness and socket extension revision 2

> **Draft review status.** This tree provides implementation and test sources.
> The complete qualification package is awaiting public disclosure authorization;
> review of this draft does not establish target qualification.

This contract extends the existing Net2 v2 envelope. It does not change syscall
numbers, socket ownership, address grants, the original operation layouts or the
first revision capability response. The network service remains a user process.

## Negotiation and compatibility

`capabilities` operation 15 with request flags zero keeps the original revision
1 response and flags mask 3. A new caller explicitly sets request flags 1 to
request revision 2. The 16-byte response then advertises readiness (1), write
shutdown (2), a retained read-only readiness page (4), and read shutdown (8).
An older service rejects this new request as invalid; the caller may then make
one ordinary revision 1 discovery request. It must not replay side effects.
The page feature is advertised only when the current kernel reports both sys88
bulk grant support and holder-local release. The service explicitly requests
query-features flag 2; legacy feature queries keep their original mask. A kernel
that rejects that opt-in cannot enable the page capability. Ordinary operations
1–18 retain their request and reply layouts.

Operation 19, `readiness_bind`, has no object, flags or payload. It is authorized
only for the current authenticated application session, not the controller's
reserved slot. Its successful 32-byte response contains revision 1, byte size
4096, the delegated grant handle, the nonzero session generation and a zero
reserved word. Repeated reads within one session return the same grant identity.
A binding failure returns the existing resources/unsupported/denied errors.

Operation 20, `shutdown_read`, takes one owned TCP connection handle and has no
payload or flags. Unknown handles are closed; another owner's handle is denied;
UDP is unsupported. A still-connecting TCP socket returns would-block. Successful
read shutdown discards queued input, subsequently acknowledges and discards peer
input, and makes receive return EOF. It does not send a TCP FIN or RST and leaves
the write half usable. Write shutdown retains operation 17. Combined libc
`SHUT_RDWR` performs write shutdown followed by read shutdown; if the second step
fails the already accepted write shutdown remains effective and is not replayed.
An orderly TCP FIN may retire the transport between those two requests. The
owned established description still accepts local read shutdown and discards
its remaining input without dereferencing a retired TCP PCB.

## Read-only shared state and lifetime

The server creates one 4096-byte sys88 grant per application session, with read,
write and delegate rights, deliberately **without manage rights**. It maps that
grant for writing and delegates only read mapping to the authenticated peer.
No PID or page address from a request grants authority. The peer chooses an
unoccupied VM arena address for its own read mapping. A map collision or resource
failure is reported; no mapping replaces an unrelated reservation.

Both peers use sys88 action 24, `grant_release`, to release only their own handle
and mappings; process exit has the same holder-local lifetime effect. The client
retains backing pages while it retains its handle. This
prevents a service death or revocation from asynchronously unmapping memory
while the client is copying a snapshot. The client checks its authenticated
endpoint before and after the copy; a closed endpoint makes the snapshot
unusable. Releasing the client handle releases its mapping. The old action 23,
`grant_close`, retains its global revoke semantics and requires manage rights;
these peers cannot invoke it successfully. Grants and mappings
remain subject to the existing sys88 per-process and global budgets. A retained
page has no connection or execution authority.

If a client's local release encounters pins, VM continuation or reservation
fragment pressure, libc retains that one retired handle and retries during
later network cleanup or open. It does not publish or read the retired page,
open a replacement session over it, or allocate an unbounded list of abandoned
pages. A new connection reports `EAGAIN` until the recoverable condition clears.
Process exit also releases the retained reference. Close does not promise that
a mapping blocked by a concurrent VM operation is removed immediately.

Only the first 128 bytes have a defined layout; the remaining grant bytes are
zero. The page contains an eight-byte sequence, four-byte revision and record
count, eight-byte session generation and sample time, then two 48-byte records.
Each record contains a connection handle, the existing 32-byte readiness snapshot
and a signed result. Records include only the session's owned connections.
Revision 2 adds read-closed bit 64 to page readiness events. The original operation
16 response masks that new bit and preserves the revision 1 event range 0–63.

The sole writer makes the sequence odd before mutation and even after publishing
all fields. Clients make a bounded copy, accepting it only if the sequence was
nonzero, even and unchanged. They bind both session generation and connection
handle. Retirement publishes an invalid odd sequence before dropping the service
mapping. A torn page, an in-progress writer or a missing record is unknown.

## `poll(0)` and finite deadlines

A consistent page is not by itself a proof of freshness. A zero-timeout poll
performs no RPC wait. It may immediately report level events from the current
owned description: buffered receive data, EOF, errors, closed directions and
write capacity hints. Client I/O and polling serialize through the network lock;
service mutations publish the updated page before their replies, so a prior
positive receive level cannot survive consumption by the same description.
Write readiness remains a hint; peer window changes can race the next write.

A negative snapshot sampled **before this poll entered** cannot prove that no
new event arrived. It returns `EAGAIN`, not zero. Zero is allowed only when a
consistent negative sample was produced during the current call. An equal
clock-tick timestamp is unknown: `sampled_ns` must be strictly greater
than the call-entry timestamp, since equality does not establish event order.
Contention or
an in-progress writer also returns `EAGAIN`. A live but stalled service therefore
cannot turn an old negative page into a successful not-ready result. An old
service without the page capability retains the explicit unsupported immediate
connected-socket path.

Finite polls use fresh read-only readiness requests and one original absolute
monotonic deadline across descriptor acquisition, service negotiation and waits.
An accepted read-only query may outlive a poll, but its identity is retained and
its late reply consumed at most once. It cannot extend that poll's deadline or
be attached to a later socket. An operation whose outcome is uncertain is never
replayed automatically. A negative timeout return is not a fresh immediate
snapshot claim.

The FD table holds the original open description for the whole poll. Each scan
checks that the caller's descriptor still denotes that description, both before
and after queries, including successful late replies. Concurrent
close or reuse produces `POLLNVAL`, without redirecting an old query to the new
FD. Close may retire the descriptor while a poll keeps the underlying object
alive; physical cleanup happens when the final lease is released. Different
Files descriptors do not acquire the Net2 transport lock.
The identity check itself may encounter the Files table lock while another
thread changes a descriptor. A finite poll retries that unknown identity under
the original deadline; it never attaches an already received event until the
identity is confirmed. Immediate polls report `EAGAIN` when this contention is
the only observation.

Each iteration first scans all supported descriptors without waiting. A known
ready Files or pipe descriptor, or a positive socket page, is reported promptly
even if an earlier socket has an unknown page or a pending service reply. Only
when no positive event is observed does a finite poll wait for fresh socket
queries. After a query uses the caller deadline, one final nonblocking scan
observes concurrent descriptor changes before returning a timeout. A positive
mixed-descriptor result lists the observed ready events; it does not certify
negative freshness for unreported sockets. An all-negative immediate result
still requires fresh negative snapshots for every connected socket.

## Nonblocking sockets and further descriptors

`SOCK_NONBLOCK` and `F_SETFL(O_NONBLOCK)` affect the shared open description,
including duplicates. A nonblocking TCP connect initiates one authorized remote
open and returns `EINPROGRESS` while TCP is connecting; another connect while
pending returns `EALREADY`. Poll observes completion and `getsockopt(SOL_SOCKET,
SO_ERROR)` reads the pending error. Other socket options remain explicitly
unsupported. Nonblocking read/write performs one service exchange and returns
`EAGAIN` on an unavailable network operation; it does not wait for data or retry
that operation. Service IPC negotiation/transport still has its own bounded
request deadline; this flag does not make user-service RPC delivery wait-free.

Regular Files descriptors preserve their established readiness behavior.
Independent pipe ends and pipe-backed stdio use the generic non-consuming sys54
query: buffered data/read EOF produces `POLLIN`, no writers produces `POLLHUP`,
free write capacity produces `POLLOUT`, and no readers produces `POLLERR`.
Console and terminal actor readiness are not inferred from pipe state and remain
unsupported by this poll profile. Unknown event classes remain unsupported.
`pthread_cancel` stays `ENOTSUP`; this work adds no POSIX cancellation delivery.

## Qualification and rollback

Qualification must bind the rebuilt SDK, service, kernel, configuration, target
program and real peer. Host packet tests supplement actual guest tests for page
read-only rights and retention, independent owners, immediate readiness, unknown
negative state, normal and late replies, nonblocking connect, both shutdown
directions, pipe EOF/backpressure and concurrent close while poll is observed
pending. Old frozen reports retain their original source and capability scope.
Rolling back requires the matching prior SDK and image; old clients can continue
to request revision 1 against the new service.
