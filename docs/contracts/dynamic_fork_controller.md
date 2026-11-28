# Dynamic fork controller ownership

The public fixed startup GNU profile supports a single-thread `fork` or `_Fork`
after its initial authenticated READY/ACK exchange. The fork child receives a
fresh controller pair owned by its direct parent. The parent keeps its own
upstream controller. A copied channel number never grants the child access to
its parent's channels.

This is the fork-to-exec protocol. Terminal actor startup and terminal channel
preservation during dynamic exec have a separate contract and qualification.
The private shared runtime without public startup retains its explicit fork
stub. Native thread-profile admission continues to reject fork with `ENOTSUP`,
including after all workers have joined. Calls from startup constructors,
before initial READY, return `EBUSY` without creating a child.

## Construction and ownership

The libc adapter serializes fork with dynamic loader operations. It verifies
that the current process owns a ready startup state, an unquarantined approved
policy, and an authenticated live upstream READY/ACK pair. It then uses native
fork prepare (57), retaining one absolute monotonic deadline five seconds in
the future. The existing Files clone operation and any existing terminal fork
registration complete while the child is still non-runnable.

The parent releases the Files transaction before controller admission: the
admission callback can itself use the same Files session. Native fork admits
only a single thread, so no other thread can mutate the descriptor snapshot in
this interval. The parent records the building child in its ordinary launch
registry, creates fresh channels, and retains the offer in its private state.
Native fork commit (58) follows only after all preceding steps and the same
deadline remain valid. Only then does the parent send one offer on the fresh
ACK channel: native IPC rejects a building receiver. A failed prepare aborts
the building child and closes its newly created controller pair; a failed
post-commit send cancels and reaps the child.

The child resets copied Files and network session state and enumerates native
channel metadata. Exactly one send endpoint and one receive endpoint must
name its direct parent as both peer and controller. It consumes a single exact
offer from that authenticated pair and verifies identity, artifact, deadline,
and all reserved fields before replacing its copied startup descriptor. It
then performs ordinary READY/ACK with its new parent. A committed child that
cannot finish adoption exits with status 127; it never returns from `fork` in a
half-initialized state. The parent returns the child PID only after READY.
The parent's READY completion means its authenticated ACK was enqueued; it
does not prove the child consumed that ACK. If the controller exits during
this final exchange, adoption can still fail with child status 127. A caller
that needs to test or rely on the child's execution after `fork` must arrange
an application acknowledgement before allowing its controller to exit.

The initial thread's native TID, thread-name state and elapsed-wait tickets are
reset by the existing `_Fork` child path. User TLS values and ordinary address
space contents retain fork copy semantics. A later successful exec keeps PID
and changes image/TLS initialization according to the existing exec contract.

## Separate fork offer

`xos/fork_control_abi.h` declares `xos_fork_control_offer`, exactly 128 bytes:

| Field | Width | Meaning |
| --- | --- | --- |
| `magic` | `u64` | `0x314b524f46534f58`, bytes `XOSFORK1` |
| `version`, `size` | two `u32` | 1 and 128 |
| `controller_pid`, `child_pid` | two `u64` | direct parent and prepared child |
| `generation`, `nonce`, `deadline` | three `u64` | generation 1, nonzero fresh nonce, shared fork deadline |
| `ready_handle`, `ack_handle` | two `u32` | exact fresh native pair |
| `artifact` | 40 bytes | inherited approved generation ID and SHA-256 |
| `reserved` | three `u64` | all zero |

The offer has its own magic and message type; it does not reinterpret any
reserved launch-control field. Its generation and nonce are subsequently
managed by the existing launch registry. Repeated adoption, malformed offers,
ambiguous native pairs, missing controllers and offers received after the
deadline fail closed. A failed send is definitive: the parent aborts rather
than replaying an ownership-changing request.

## Exec, wait and failure

The child's subsequent exec PREPARE is addressed to its new direct parent.
The parent admits only already approved artifact identities and drives
PREPARE, cancellation, READY and completion while inside public wait calls.
`waitpid(..., WNOHANG)` also pumps the controller. Blocking unrelated I/O does
not implicitly run a controller; programs must arrange their control and data
flow accordingly. Nested fork-to-exec repeats the same relationship at each
parent, without migrating the ancestor's own pair.

Failed exec keeps the old image, PID, descriptors and active control identity.
A successful exec preserves the existing CLOEXEC rules, shared open-file
descriptions and independently held pipe references. This protocol does not
add create authority: fork follows native admission, and same-PID replacement
retains the current authority. Ordinary controller death closes its channels;
surviving children cannot obtain another approved replacement from that dead
controller. Explicit parent cancellation uses the existing descendant cleanup
rules.

Every registration, channel, Files reference and pipe reference remains under
its existing native owner and budget. Fork does not increase the native
generic-channel quota, launch registry capacity, maximum process/thread count,
or descriptor limit. Readiness failure after commit cancels and reaps the
owned child before returning an error. Cleanup does not recycle uncertain
control state into a new generation.

## Qualification boundary

The focused host fixture includes the production adapter and models its kernel
and launch-policy boundaries. It checks fresh adoption, duplicate/late offers,
metadata authentication, malformed fields, bounded rejection and parent
cleanup. Its report does not stand in for an actual target run.

The target fixture binds a fresh system, C SDK, shared GNU runtime, approved
launcher and two C generations. It covers fork/exec, nested controllers,
denied create authority, controller death/cancellation, PID/TLS/FD rules and
independent pipe alias/CLOEXEC/EOF/EPIPE behavior. The C-only generation has no
approved libgcc unwinder: its thread-profile rejection case does not claim
successful GNU worker creation or worker TLS cleanup. Actual target results
and their exact artifact/source bindings belong in the accompanying report.
