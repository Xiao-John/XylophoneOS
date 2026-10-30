# SSG-P1: restricted prewired cross-process observation

This is a **read-only experiment**, not a session-wide broker or a security
boundary. An authorized session parent creates two existing XOS pipes and starts
one consumer and one cooperating GUI provider as separate children. The parent
passes only the required ends at process creation and closes its copies. The
provider reads its own live Qt Widgets or liteHTML model on the GUI thread;
the consumer parses the reply in its own address space. Serial/console output
is diagnostic evidence, not the request/response channel.

The model and any text returned by an application do not approve observation or
action. There is no discovery of unrelated running applications, per-message
kernel authentication, access-control service, remote revocation, subscription,
reconnect, cross-process action execution or production broker here. The parent
must already have legitimate child-spawn authority. A shell child without that
delegation fails; this experiment does not widen the shell's authority. See
[upstream probe #30](https://github.com/Xiao-John/XylophoneOS/pull/30) for the
independent real-guest pipe and attempted running-child rewire evidence. That
Draft PR and the SDK/SSG prerequisites remain separate review units.

## Connection and authority

The parent explicitly wires provider stdin to the consumer's request pipe and
provider stderr to the consumer's response pipe, with the opposite ends at the
consumer. stdout remains a diagnostic console. The provider installs a Qt message
handler before Qt startup so Qt diagnostics do not share the binary route; other
unexpected writes on that route can still corrupt the protocol, which causes a
connection failure. This is one reason it is not a production endpoint. Neither
console output nor the process's self-reported name/PID authenticates a peer.
The prototype CLI logs the full received frames to stdout, including authorized
text; the saved tests use synthetic documents. Do not treat those diagnostics
as a privacy-preserving production logging system.

`--text` is an explicit session-launch choice. Without it, Notes returns ordinary
metadata with `NOT_AUTHORIZED` for text; Browser's current text-bearing provider
returns `DENIED`. With it, text is authorized only within this cooperating
provider's application/document scope. `QtScene` continues to withhold password
QLineEdit values and selections even with normal text enabled. A trusted Qt
application can also set `xosSsgProtected=true` on a widget; its subtree then
withholds text, accessible/object names and widget-specific values, including
for role-filtered queries. This is an application-supplied classification, not
an independent security boundary. Do not infer that unmarked protected or
app-defined sensitive content has been classified; this is not a complete
sensitive-data system. The application host, not an AI output, selects scope.
When Browser's legacy local probe and a prewired session are both enabled,
the local probe is refused if the pipe did not receive text scope; it cannot
enable text for that consumer.

The parent asks the existing random-byte interface for a fresh 128-bit
`sourceInstance`; failure prevents session startup. It is a collision-resistant
session discriminator, not authentication, a grant, or proof of the executable's
identity. A snapshot also has the existing provider `sourceEpoch`, `sceneVersion`
and node IDs. A detail operation requires the current instance, epoch, scene
version and node ID; a stale scene version is refused. A replaced instance or
epoch is refused. Diff requires the original scope and retained history;
truncation or a changed scope yields `RESET_REQUIRED`, and `removed` means
leaving that query result, not necessarily destruction. Within an epoch Qt uses
QPointer-backed identities; Browser navigation/reload replaces its scene epoch.
The parent records the actual child PIDs returned by spawn, while each provider
and consumer also reports its PID for correlation. None of these values provides
per-message peer authentication or survives a restart as an authority.

## Framing, threading and failures

The private protocol is a byte stream: four ASCII bytes `SSG1`, an unsigned
little-endian 32-bit JSON byte length, an unsigned little-endian request sequence,
then UTF-8 JSON. Request frames are limited to 4096 bytes and response frames to
81920 bytes; the existing SSG node/text/depth/serialization limits still apply.
One request is outstanding per connection. Sequence zero and sequences no newer
than the last accepted one return `STALE_MESSAGE` without executing a query.
This counter prevents accidental replay on this connection; it is not a nonce or
an authentication mechanism. Invalid lengths/magic, incomplete frames, EOF and
broken routes terminate the connection. Short reads/writes are assembled and
would-block waits on existing pipe readiness; no busy polling runs on the GUI
thread. One worker receives and writes bytes and posts a single bounded query to
the Qt event loop. Only the GUI callback touches Widgets/liteHTML.

The consumer's helper waits on the existing monotonic deadline mechanism and
closes its local routes when a response stalls. The provider uses one GUI-owned
single-shot timer to close its local routes for a stalled partial frame or write.
The provider timer depends on a responsive event loop and does not bound a hung
GUI callback; it is not a hard real-time guarantee. An idle provider waits for
its next first byte without a deadline. The application closes its routes and
joins its worker on exit; either peer's death invalidates the connection. Closing
a route does not revoke other independently held references. No generic wait-any
or deadline-enabled pipe operation is asserted.

`ssg-consumer` offers `root`, `snapshot [role]`, `visible`, `visible-text`,
`clickable`, `detail [role] [id]`, `diff [role] [seconds]` and `watch [role]
[seconds]`. For Browser, add `browser` to the `visible-text` or `clickable`
mode. `detail` first obtains a scoped snapshot on the same connection. `diff`
and `watch` query again on that same connection and resnapshot if a reset or
source replacement is reported. The CLI never executes an action. Explicit
`ref-detail` and `ref-diff` modes submit a recorded reference to check it;
starting a new session cannot make an old instance valid.
The Browser acceptance consumer makes at most four spaced attempts to obtain a
complete baseline. If a subsequent diff requires reset, it resnapshots and
observes another real scroll; it never turns a capped result into a complete diff.
These retries do not guarantee completion: an existing larger-page Browser
regression remained capped in two candidate runs and in a frozen baseline
comparison on the same guest image. Pagination or another bounded continuation
needs its own design and qualification. The passing cross-process run obtained
a complete baseline on its first attempt; its bounded retry/recovery branch was
not exercised by that run.

Qt visibility is local widget visibility, not global compositor occlusion; a
QPlainTextEdit returns a bounded **document prefix**, not an exact set of
visible glyphs. The `visible-text` mode for Qt shows text of visible labels, not
an exact per-glyph visibility guarantee. Browser text/link visibility uses actual
bounded layout fragments clipped to its viewport, and a partial fragment or
capped traversal keeps its uncertainty. Partly clipped text can contain characters
outside the visible fragments. No result implies whole-screen visibility.

## Production direction, not implemented here

A reviewed generic user-space Semantic Broker would need authenticated dynamic
peer establishment, discovery independent of observation rights, explicit
user/session policy, attenuated text and sensitivity scopes, bounded streaming,
monotonic deadlines, disconnect/revocation, lifecycle generations and independent
verification of typed actions. The existing pipes cannot establish all of these
properties for arbitrary already-running peers. The missing generic mechanisms
must be independently reviewed under C19–C29 before implementation; no
SSG-specific syscall or Linux-interface clone is proposed here.

Future providers should prefer native structured data where it actually exists:
Qt widgets and custom components with their own semantic provider; authorized
XOS desktop/system surfaces; Browser DOM/layout/render fragments, including
future dynamic DOM/iframe/Shadow DOM only when the engine and authorization
support them. Canvas and WebGL pixels do not automatically contain accessible
semantics. For video, captions, timelines and frame streams, establish authorized
native media channels, then allow a future vision model to infer meaning from
frames with provenance and uncertainty. Typed actions require trusted approval,
target revalidation and independently verifiable receipts. LocalPilot would be
an ordinary consumer of those reviewed interfaces, with no special kernel right
or second agent runtime.
