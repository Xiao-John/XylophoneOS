# ClarkE full-page renderer lifecycle, revision 1

## Scope and authority

This profile uses actual WebCore layout/painting and a Qt raster viewport. A
trusted Xsh controller pins three fixed installation receipts: UI, network
broker and renderer. A UI navigation contains a bounded URL and increasing
navigation number. It carries no executable path, PID, capability or grant.
The UI receives no network service PID. The broker is an ordinary net2 client;
only Xsh retains the service's authenticated bootstrap-controller identity.

The controller installs a version-1 cumulative process-tree budget with
`set_process_budget` in `prepare_child`. It queries the child-owned domain and
compares all six limits before allowing startup. Renderer raw networking is
revoked through existing net2 operation 8 before the child becomes runnable.
A denied, failed or unknown policy result prevents launch. Neither environment
variable omission nor renderer cooperation is the network enforcement boundary.

## Private bootstrap and transport

The application protocol is revision 1 (`0x314b4c43`), with a 32-byte header,
4096-byte packet limit, 64 KiB document limit and 320 × 180 RGBA viewport.
Every message is checked for exact length, operation, navigation, sequence of
offsets and payload shape. Complete documents and frames carry SHA-256 digests.
No partially received frame replaces the visible page. Qt acknowledges a frame
only after its exposed window has flushed the actual backing store. The QPA
records the actual Interactium commit result and a per-window serial. A same-process,
GUI-thread-only revision-1 receipt (24 bytes: version, size, serial, result)
lets the viewport require an advanced serial and zero result before `presented`.
This is not a new kernel syscall or Interactium wire operation. A void Qt flush
call alone is insufficient evidence that presentation succeeded.

The parent creates two short-lived sys81 one-way bootstrap channels before
startup. The child checks their kernel-reported peer and controller PID, creates
its own sys84 private pair and returns the reversed endpoints. The parent checks
both endpoints against the actual spawned child PID, validates the unchanged
configuration and consumes a private READY. It then closes both bootstrap
channels. Each worker owns its runtime pair, avoiding multiplication of the
parent's four-pair quota. Messages and argv alone never authenticate endpoints.

The UI, broker and renderer have independent lifetimes. Navigation creates a
fresh broker and renderer. A replacement navigation or cancellation retires
the previous workers before starting another navigation. Every wait and IPC
operation has a finite monotonic deadline. Failure closes the partial frame and
reaps owned children. A renderer sends its completed frame, waits for a private
frame acceptance and then exits; it cannot close away an unconsumed final frame.
Likewise, the UI sends `close` and waits at most three seconds for the controller's
exact empty `close` acknowledgement before normal exit. The controller acknowledges
before waiting for UI retirement. This preserves the close message until it is
consumed instead of racing it against destruction of the child's owned pair.

## net2 peer policy extension

Wire version 2 gains operation 21, with an independent revision-1 payload:

| Structure | Fields | Size |
| --- | --- | --- |
| Request | `u32 revision, size, action, reserved` | 16 bytes |
| Snapshot | `u32 revision, size, occupied, capacity` | 16 bytes |

Only the kernel-authenticated bootstrap controller may call it. Action 0 queries
the bounded denial table and requires object zero. Action 1 releases a retired
PID's denial; object must be nonzero and different from the controller. Unknown
actions/revisions, nonzero reserved fields, unrelated flags, address, port or
protocol fields are rejected. Release is idempotent. Ordinary clients cannot
query or remove policy, including a broker that can make ordinary connections.
The existing 16-entry limit, revoke semantics and capabilities flags remain.
Old servers reject operation 21; callers fail closed rather than assuming reuse.

The controller may release only after a successful public wait for its owned
child, or a positive never-started/abort result below. It may reconnect and retry
an idempotent revoke or release once after a closed, IO or timeout result. An
uncertain revoke is retained until retirement is proved. This trusted-controller
rule is not an assertion that the network service can independently query process
death; operation 21 grants no new authority to an ordinary peer.

## Explicit loader abort result

`spawn_verified_static_file` validates the fixed receipt and uses the existing
static loader without invoking the dynamic hook. It rejects same-PID exec.
`launch_abort_outcome` is an independent 32-byte, version-1 output containing
version, size, PID, never-started, abort-attempted and the raw kernel abort result.
Existing `spawn_options`, runtime hooks and legacy entrypoints keep their layout
and behavior. Callers must link the matching SDK source for the new entrypoint.

Every path initializes the output. Before successful process creation there is
no PID and no attempted abort. Creation records the PID and never-started state.
A successful start clears that state. Failure records the actual abort syscall,
including failure. Cleanup is confirmed only when the recorded PID equals the
prepared child, never-started and abort-attempted are both one, and abort returned
zero. A negative spawn result is insufficient. Unknown/failed abort retains the
denial, emits failure and ends the browser session.

## Controlled HTTPS boundary

The network broker uses the actual OpenSSL port over a bounded native net2 BIO.
Its build pins one DNS origin, one IPv4 route and an explicit DER CA. TLS requires
chain and hostname verification, SNI, the normal certificate validity check and
at least TLS 1.2. HTTP framing is bounded, redirects are disabled and only a
complete response is forwarded to the renderer. This profile does not claim DNS
resolution, a public CA store or unrestricted internet browsing.

The entire exchange, including shutdown, shares one three-second monotonic
deadline, 4096 transport calls and 512 KiB of wire traffic. A blocking
`SSL_shutdown` returning zero means the local close notification has been sent;
the broker makes one further bounded call to receive the peer notification.
It accepts only return one and does not treat unauthenticated EOF as success.
Failures clear the response and close the native client. The isolated TLS guest
uses this same production fetcher and tests both shutdown orders, a withheld
notification, transport truncation and invalid certificate chains/names/dates.

## Qualification requirements

The qualification must observe raw renderer attach refusal while the live
ordinary broker succeeds, unauthorized operation-21 release refusal, more than
16 real navigation lifetimes, cancel and renderer fault cleanup, and process
and policy capacity recovery. DOM/CSS fixture geometry and pixels come from
actual WebCore and viewport evidence comes from actual Qt scanout.

Two isolated compile flags exercise real failure boundaries:
`XOS_LOADER_TEST_BAD_START_ENTRY` changes the post-prepare entry to unmapped zero,
and `XOS_CLARKE_TEST_FAULT_NAVIGATION` traps the selected diagnostic navigation.
Production builds contain neither branch. Their exact source, flags and ELF
digests must be recorded. A callback that aborts first is the negative case:
the loader's second abort fails, so no denial may be reclaimed by inference.

This contract's reconstructed source checkpoint does not claim guest acceptance;
the current execution status is in the P1-F work log.
