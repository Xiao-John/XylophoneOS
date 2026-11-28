# Mobius copied multiwindow profile

This profile uses the deployed Interactium user-space service and its existing
wire version 1. It allocates no syscall, display action, wire operation, or
reserved field. The final scanout remains one exclusive display-v1 client.
Applications have separate authenticated IPC sessions and private RAM; the
compositor receives copied pixels, never client virtual addresses.

## Authority, compatibility and bounds

The service accepts at most four sessions through sys84–86. The kernel supplies
the endpoint peer PID. A session token belongs to that peer and a window token
belongs to its session; putting another token in a request cannot grant access.
Create, configure, focus, frame submission, input retrieval, close and destroy
all check this ownership. Reconnecting creates a new session. Service exit or
successful exec revokes the endpoints; a new service PID cannot answer an old
session. The ordinary SDK client additionally checks both endpoint peers against
the service PID supplied by its controller, and checks reply sequence, session,
object, type, sizes and reserved fields.

The wire header remains 48 bytes, little-endian, with messages at most 4096 bytes.
Header flags and reserved fields are zero. Client capability requests are zero;
the only pixel format is premultiplied ARGB8888. Titles are not transmitted in
the current fixed create payload, so `title_length` must be zero. Each session
has at most eight window records. The deployed drawable pool is **eight surfaces
globally**, not eight surfaces for each client. Exhaustion returns a resource
failure without evicting existing surfaces. The service has two 800×600 buffers
per drawable surface and one 800×600 scanout buffer: 32,640,000 pixel-storage
bytes in total. Smaller windows use that bounded pool. No shared writable
mapping, GPU queue, screen capture, clipboard or cross-application readback is
provided.

Existing Qt QPA clients use zero flags/reserved fields, copied tiles and the same
operations. Their valid requests remain valid. Legacy `display_client` and
`gfxdemo` keep their exclusive v1 path: a direct second display client remains
busy while the compositor owns scanout. This profile does not change legacy
display-v1 ABI or relabel its old single-surface evidence as multiwindow evidence.

## Frame and geometry rules

`begin_frame` requires the current window dimensions, a whole-pixel stride,
bounded bytes and a frame serial newer than the last accepted serial. There is
one pending frame per session. The service first copies its accepted private
front buffer to staging, so a submitted tile may update only part of a frame.
Unsubmitted pixels retain their accepted values. A tile's complete bounds,
source offset, length and premultiplied channels are validated before any pixel
in that tile changes. Each channel must be no greater than alpha.

`commit_frame` makes staging visible only after the full request validates.
`cancel_frame` discards staging without changing the front. A commit reply means
accepted, not vertical-blank presentation or persistence. Damage comes from the
actual accepted tile rectangles, including writes omitted from a client's dirty
hint. The compositor combines affected bounds and recomposes every intersecting
layer in z-order, then submits only that display rectangle. Premultiplied
source-over uses integer encoded-sRGB channels with `(channel * inverse + 127) /
255`; it does not claim linear-light colour management.

Configure permits position, positive size within 800×600 and `flag_visible`.
Unknown configure flags are rejected. Successful configure retires an in-flight
frame for that window: its later tiles or commit are stale and rejected. Resize
preserves only the intersection of the old and new sizes, initializes newly
exposed pixels to the profile background and clears discarded pixels. Shrinking
then expanding cannot reveal old, hidden pixel data. Old and new extents are
damaged; hiding, closing and owner loss also repair the uncovered area.

The old implementation acknowledged `close_request` without changing state.
It now performs an owner-authorized close: it destroys that client's window,
retires its pending frame and input, and returns an acknowledgement. A foreign
or stale token is denied. It does not terminate the process or grant authority
to close another application's window. Applications may instead use the existing
`destroy_window` operation. The stricter validation and effective close replace
undefined or false-success behaviour; no supported nonzero field is repurposed.

## Input ownership and failures

A real pointer press focuses and raises its hit-tested window. An application
may request focus for one of its own visible windows. Keyboard presses and their
repeats remain assigned to the original press owner until release, including a
focus change. If that window disappears, its release is discarded. A held
pointer gesture is captured by its initial press window until every button is
released. Crossing another window does not deliver that gesture to it. Pointer
leave notifications carry no pressed buttons. Loss, hide or destruction of the
capture owner suppresses the remaining held gesture; a fresh press is needed
after release. Hidden windows receive no new input.

Per-window monotonic input sequences, the bounded event queue and explicit
resync/loss reports remain in use. Closing the focused window selects the
topmost remaining visible window. Disconnect, fault, kill and successful exec
invalidate all of a peer's windows, input and staged frames. The next service
scan repairs their pixels without affecting another peer's accepted frame.

Malformed framing for which an authenticated response cannot be constructed
closes only that session. A synchronous caller observes the revoked transport
instead of waiting forever. Ordinary operation errors receive a typed status.
The SDK client serializes one transaction per instance through its caller; it
does not provide an internal cross-thread mutex. Its send and receive waits
share the caller's **original absolute monotonic deadline**. Timeout, malformed
reply, changed peer or transport loss closes the session. An uncertain mutation
is never retried automatically. A controller may create a new service and
explicitly rebuild a new session, without silently restoring old capabilities.

Display v1 and named IPC currently have no shared wait set. The production
service performs a bounded fair scan of each active client and the input source;
when no work progressed, it sleeps for 10 ms on the existing monotonic timer.
This is an explicit polling cadence, not an event-notification or zero-wakeup
claim. A slow client cannot hold the service in a client-specific blocking wait.

## Build and qualification

Use the matching ordinary SDK to compile
`scripts/build_mobius_multiwindow_probe.py`, then run
`tests/mobius_multiwindow_guest.py`. Its two applications have different PIDs and
different endpoint sessions. QEMU PS/2 events and actual scanout images cover
overlap, focus, partial frame visibility, cancel/commit, resize/move, ownership,
one application faulting while staging, service loss, fresh service recovery and
the retained exclusive display path. Source, SDK, image and tool identities are
bound by the runner; resource counters must return exactly to their baselines.

`tests/mobius_multiwindow_host.py` runs the existing Interactium model, transport
and demo regressions plus full-reference-versus-damage comparison and protocol
negative cases under ASan/UBSan. LeakSanitizer is separately labelled unavailable
on the current ptraced host; target resource return is measured independently.

The SDK manifest describes implementation, with qualification belonging to a
matching run. An optional independently rebuilt threading SDK can compile and
run the same protocol consumer with its own `crt0_posix.o`, matching threaded
newlib and `libxos.a`. That profile exercises a real pthread, separate TLS/errno,
and join before window creation; it does not qualify a C++ standard library or
concurrent calls on one client instance. Qt package rebuilds,
installed Mobius/ClarkE combinations, glass effects, physical GPU hardware, SMP
and long stress retain separate evidence requirements.

The matching P1-G ordinary and threading SDK qualification is recorded in the
[2026-11-28 report](../reports/p1_g_multiwindow_20261128/README.md). Its source,
runtime and image bindings delimit that result; it does not upgrade unrelated
SDK producer receipts or earlier single-surface evidence.
