# Aurora Compositor G2 — review proposal, not an allocated ABI

2026-10-30. Base `3377dbf`. **PROPOSED / NOT IMPLEMENTED / NOT APPROVED.**
This document requests architectural review of the missing transport and service
lifecycle. It allocates no syscall, display action, service operation or SDK capability.
The [ABI registry](abi_registry.md), C19–C29 and [time domains](time_domains.md)
remain authoritative. No new graphics mechanism is implemented in this branch.

## Concrete insufficiency and consumers

Display v1 (`display_abi.hpp`) accepts one client, XRGB8888 RAM and a 64-byte
request / 96-byte reply. `sys_display_present` copies an authenticated client's
pixels to final scanout; it cannot deliver that RAM to another userspace process.
A compositor owning that client prevents any second current QPA client connecting.
There is no admitted ARGB window, window ID, cross-process backdrop request or
per-window input channel. `tests/fixtures/qt6/compositor_gap.cpp` exercises only
existing v1 calls: free connection, occupied connection (-16), ordinary direct
present denial (-1), and close. The guest runner runs it while a separate desktop
process owns the Surface. This proves a blocking gap, not a multiwindow implementation.

Current generic send/receive is also insufficient for arbitrary app→compositor:
`src/kernel/arch/x86_64/tasks.cpp` fixes 21 endpoint slots, default 64-byte messages,
4096-byte backing storage, sender/receiver/owner identities and one pending message.
4096-byte capacity and richer routing are attached to the file-service session;
applications cannot repurpose those identities/rights as a graphics transport.
There is no public create/bind/grant/wait-any for arbitrary peer services. Existing
process-creation memory mapping is for constructing a child, not sharing two live
application heaps. Anonymous VM proposal 67 does not grant interprocess sharing.

Actual next consumers: two independent Qt applications (Notes plus SDK Studio),
then Browser; later transparent pet/bubble windows and a WebView host. Legacy QPA
and `gfxdemo` must retain an explicit v1 exclusive path. No implicit interception
of their pixels, changed syscall numbers or silently relaxed permissions.

## Candidate placement

```text
unprivileged Qt apps -- controlled copied window messages --> Aurora Compositor
                                                           | composition + input policy
                                                           | existing v1 display_client
                                                        Display Service --> scanout
session parent -- explicit generic endpoint grants ---------^
```

The compositor is a userspace service trusted with its session's submitted pixels
and input. The kernel may mediate identity, endpoint rights, bounded copying,
waiting and revocation. It must not interpret window/material/z-order/Qt policies.
The existing display service's final output is sufficient in principle; its
inherited kernel VBE/VirtIO-GPU driver debt remains registered, not newly excused.
G2 adds no device/MMIO/DMA rights. C28 driver migration stays a separate review.

First investigate a **generic** endpoint create/grant/revoke + bounded copied
message mechanism with authenticated sender and disconnect notification. Review
whether one wait primitive can cover IPC, shutdown and monotonic deadlines. Prefer
reuse/extension of existing mechanisms where their exact ownership permits it;
do not add a compositor-specific syscall, file-service proxy or guessed number.
Before implementation: a separate registry/contract PR must specify concrete
layouts, rights attenuation, wait races, handle generation and old callers.

## Proposed userspace window protocol semantics

Symbolic operations below intentionally have no wire numbers. After transport
review, freeze a separately versioned wire header with fixed widths: u32 version,
u32 size, u64 request sequence, u64 session epoch, u64 object token, u32 payload
length, u32 flags. Integer byte order must be little-endian for this x86-64 profile;
all reserved bits zero, exact lengths checked. No Qt pointers, C++ object layouts,
self-reported identity, device addresses or persistent client virtual addresses.

| Operation | Authority and validation | Result / lifecycle |
|---|---|---|
| HELLO | Endpoint grant binds caller to approved service epoch; negotiate version and quotas | Session token, dimensions, supported features; unsupported version rejects |
| CREATE | Sender owns session; bounded dimensions, normal/overlay role only if granted | Fresh token bound to owner + epoch + generation; metadata has no readback right |
| BEGIN_FRAME | Owner, increasing sequence, ARGB8888 premultiplied sRGB bytes, validated width/stride/byte length | One pending frame; previous complete frame stays visible |
| WRITE_TILE | Owner + frame token; bounded rect/offset, no overflow or duplicate conflict | Copied bytes into admitted private staging memory, never client VA dereference |
| COMMIT_FRAME | All required bytes present; dirty bounds and declared opacity verified | Atomic front/staging swap; ack means accepted, not vblank or durable state |
| CANCEL_FRAME | Owner; stale/unknown token rejects | Free staging; previous front retained |
| SET_GLASS_REGION | Owner can request an effect behind its own bounded content region | Compositor samples lower layers internally; no background pixels returned |
| CONFIGURE | Client requests size/state; compositor applies policy within limits | Serial configure + ack; old size valid until committed matching frame |
| SET_INPUT_REGION | Owner; region confined to own bounds; default full rect | Passthrough affects hit test only, never grants synthetic input |
| DESTROY / CLOSE | Owner destroy; shell close is a request, with process termination separate | Revoke token, cancel pending frame, detach input and free owned copies |
| INPUT / FOCUS | Sent by compositor from exclusive real input source | Per-window local coords + global sequence; loss causes explicit resync |
| DISCONNECT | Authenticated transport lifecycle | All client objects invalidated; no stale token aliases a later owner |

Premultiplied ARGB is an *application protocol* proposal, not a change to v1 XRGB
scanout. Validate each RGB channel ≤ alpha and define malformed alpha rejection;
reference source-over uses the same encoded sRGB arithmetic for deterministic CPU
reference output, explicitly not physically linear-light optics. Opaque content
must not be trusted for occlusion until pixels/region declarations are validated.
Straight-alpha, HDR, color management and GPU surfaces are later explicit features.

For first review profile: at most two admitted GUI clients, one window each,
maximum 800×600, two 1,920,000-byte copies per window (front/staging), ≤32 MiB
total compositor image/cache admission. No allocation before quota checks. Bound
dirty rectangles (≤16), input regions (≤8), queued control messages (≤16/client),
one outstanding frame/client and nonblocking submit with explicit AGAIN. All
dimensions/stride/product/rect additions use checked u64 arithmetic; pool exhaustion
returns a resource error without dropping the previous accepted frame. These are
proposed budgets, requiring measurement before final contract acceptance.

A copied 800×600 frame is 1,920,000 bytes. At a hypothetical 3072-byte tile payload
it needs 625 payload messages plus frame control. Current 64-byte default endpoints
cannot support this profile; 4096-byte file endpoints are not a lawful shortcut.
Latency/bandwidth/CPU cost is **NOT MEASURED**. First measure this copied path; if
unacceptable, submit a separate immutable/shared-buffer contract with ownership,
mapping bounds, pin/ack lifetime, revocation races and no writable alias TOCTOU.
No assumed shared VRAM, zero-copy, GPU queue or DMA access.

## Focus, policy and protected observation

Shell requests position/layer/minimize/restore through its separately attenuated
session policy role; ordinary applications cannot raise over trusted permission
surfaces or read global input. Compositor alone performs z-order, clipping,
exclusive focus and hit testing. Drag/resizing require pointer capture tied to
the triggering real press, released on up/resync/fault. Minimized windows receive
no input. Close may be refused for unsaved content; force termination is a separate
authorized process action. No app can claim shell status by its name or PID field.

Overlay role is bounded: transparency, explicit input region, focus policy, screen
constraints and bubble relation. Click-through routes a real click to the next
hit-tested window; it never authorizes observation/capture/control of that window.
Capture/Computer Use need a separate user-approved lease bound to target token,
operation set, expiry in system monotonic time and revocation epoch. Minimize,
owner exit, target replacement, scope loss and lease revocation invalidate it.
No capture protocol is implemented here. Clipboard, file selection and notification
brokering likewise require explicit service contracts; theme does not grant them.

## Failure, waiting and epochs

Client exit/kill/fault/exec: transport invalidation cancels frames, removes all
owned windows and input capture, clears queued events and returns owned memory.
Compositor death: revoke sessions, fail waiting clients with service-lost, retain
serial rescue; supervisor may restart a fresh epoch. No transparent preservation
of unsent pixels, focus, clipboard, capture leases or approval state is promised.
Lost commit reply is UNKNOWN; query the accepted frame sequence after authenticated
reconnection if supported, otherwise rebuild state. Never blindly replay mutations.

Teardown must wake every blocked transport wait. Monotonic deadlines use the
existing system clock; retry/AGAIN preserves the original absolute deadline.
Rendering animation may use a documented pausable application time derived from
that clock; it cannot replace deadlines, update PIT/EOI or spin for frame timing.
Initially event-driven damage only, no permanent animation timer or poll loop.

## CPU glass reference and acceptance before G3

Compose back to front into compositor-owned RAM. For each glass region, sample
only already composed lower layers, expand source damage by the blur radius,
clip to display/region edges using specified clamped-edge sampling, blur into
bounded scratch, then apply tint/opacity, continuous corners, edges and shadow.
Paint the owning app's content afterward. Avoid sampling a previous version of
the same glass or feeding its own result back into the blur. Track old and new
window/shadow extents on movement; invalidate all intersecting upper glass
regions, including their sampling halo. Never expose sampled lower pixels to apps.

Required separate real-guest gate after approval:

1. Two actual independent GUI PIDs, distinct submitted content and authenticated
   ownership; one moves below a stationary upper glass region. Compare fresh
   software reference pixels after every move; no static wallpaper substitute.
2. Source-over pixel vectors (alpha 0/128/255), blur edge vectors, clipped/offscreen
   damage, overlapping glass, dirty versus full reference equality and restoration
   of old window extents. Record frame/SDK/image hashes and actual QEMU scanout.
3. Forged/stale token, wrong owner, bad epoch/sequence/version, malformed tiles,
   overflow/stride/size, full queue/quota/OOM, partially submitted frame and invalid
   alpha; rejection must leave old front intact and cannot read another window.
4. Drag/resize/minimize/restore/close, keyboard-only switch, click-through overlays,
   focus-loss/resync, process/service kill during copy/commit/wait; exact counters,
   serial/file service survival and fresh-epoch recovery.
5. Actual submit-to-visible timing, damaged area/bytes, sampled memory/threads,
   bounded queue behavior and idle wake rate at 800×600; larger mode is a separate
   boot configuration/gate, not inferred from an 800×600 screenshot.
6. Legacy v1 gfxdemo, QtCore/Gui/Widgets, Notes persistence and Browser navigation
   on the affected combination; both xsh and dash launch/error paths. C28 driver
   compliance, SMP/hardware/DMA, GPU shaders and long stress remain separate.

**Next executable work:** review this transport gap with the minimal guest probe;
register the approved generic endpoint/lifetime contract in its own PR; implement
and qualify that mechanism; only then implement the two-client copied CPU
compositor and the new QPA transport as separately reviewable changes.
