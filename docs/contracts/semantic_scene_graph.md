# XOS Semantic Scene Graph — application-local v1 prototype

2026-10-30. Userspace only. **No kernel/shared ABI change.** This round delivers
bounded read-only native providers and a separate local Intent test adapter.
Cross-process broker, production authority, subscriptions, global compositor
scene, screen observation and cross-process action execution are **BLOCKED / NOT_RUN**.
Neither the model nor an SSG snapshot grants authority.

## Implemented sources and actual limits

| Provider | Native source | Actual observation / unsupported coverage |
|---|---|---|
| `QtScene` | Real QObject/QWidget child relations, QLineEdit, QPlainTextEdit, labels, buttons and scrollbars | Parent/object IDs, native class/name, text within explicit scope, enabled/focus/check/selection/scroll state, local geometry and Qt visible region; arbitrary custom painting returns SEMANTICS_UNAVAILABLE |
| Notes opt-in probe | Its actual live Widgets and QTextDocument/cursor | File-path field, real document prefix/length, selection and scroll; document text is explicitly not all screen-visible |
| Browser opt-in probe | Real liteHTML DOM/element model, computed display and actual render fragments | Text leaf ranges, element/parent IDs, links, viewport/scroll geometry, actual engine mouse-hit state; no AX-only substitution |
| Independent example | Standard Widgets + public archive, no copied provider code | Password/hidden control checks, snapshot/diff and local Intent demonstration |

The browser patch adds bounded read-only access to the pinned engine's existing
render fragments. Original tar/member hashes remain verified; the patch is applied
only to a private build copy and recorded in the receipt. No engine layout,
navigation policy, document CSS or event behavior is altered by the accessor.
Current engine admission rejects forms, iframe, canvas, scripts and unsupported
markup. Shadow DOM, modern JS DOM and cross-origin frame traversal do not exist
in this browser. They are not bypassed through privileged reading.

Browser nodes distinguish `not-rendered`, `scroll-required`, `viewport-partial`
and `viewport-visible` using actual render boxes clipped to the viewport after
scroll translation. These statuses concern this admitted normal-flow engine
subset; external screen occlusion remains UNKNOWN_NO_COMPOSITOR. Fragments and
their completeness are returned instead of treating a DOM node as necessarily
seen. Current pointer hit identity comes from the actual engine's mouse state,
not a fabricated coordinate lookup. Unvisited/capped nodes are not inferred.

Qt nodes distinguish hidden, locally clipped/occluded and locally visible, with
local bounds, bounded visible-region fragments and their completeness. A bounding rectangle can include holes;
it is not a guarantee that every point hits that control. There is no global
window occlusion answer. QPlainTextEdit text is a bounded document prefix with
document length, selection and scroll; the provider does not label every document
character as currently rendered. Rich text/custom widgets require their own
semantic provider for more precise meaning. Drawing commands alone are not meaning.

## Ownership, identity, query and bounded diff

All provider/Intent calls run on the GUI thread; no thread-safe or cross-process
call interface is implied. A trusted host must marshal worker proposals as data.

`QtScene` holds a QPointer to its application root and bounded QPointers for node
identities. Nothing scans another process, maps its heap, reads scanout, obtains
MMIO/DMA or elevates an application. Default observation is DENIED. The trusted
application host explicitly enables text scope or revokes it; this API is an
in-process adapter, not proof that an untrusted same-process plugin is isolated.
Normal Notes/Browser export nothing unless launched with `--ssg-probe` and queried
with Ctrl+I (Notes also emits its initial opt-in snapshot). Guest probes use only
synthetic documents and serial output to the authorized test harness. They create
no global endpoint or publicly readable scene file.

A reference consists of source epoch + node ID + scene version. Epochs include
the running process identity and provider generation, not a guessed PID field
supplied by a consumer. Node IDs are not reused within an epoch. A QPointer clears
on widget destruction; a new widget gets a new ID even if its address is reused.
Navigation/reload uses a new browser provider/document epoch. Revocation clears
stored scenes and changes epoch. A diff query from another epoch returns
SOURCE_REPLACED (or unavailable after revocation), not a misleading empty diff.
IDs are not secrets and convey no authority. Production broker identities need
kernel-authenticated transport and service-instance lifecycle, currently missing.

The snapshot has version, source epoch, scene version, canonical monotonic
observation time, source/metadata, query scope and a capped flag. Integer identity
and clock values are decimal strings to preserve width in future JS consumers.
Native names, document text and labels are untrusted application content, never
instructions or authorizations. Password QLineEdit values and selections are
withheld even when normal text observation is enabled.

Queries can filter visible nodes and role; Notes prioritizes a document-role query after its initial bounded tree export, and Browser uses a body-text/link content query. Filtering avoids formatting every unrelated control; a capped whole-tree export is never treated as complete.

The retained stream keeps only current and previous states. A successful diff
returns changed/new nodes, IDs that left the *query result*, current metadata and
the `capped` state. `removed` is not proof of object destruction: a node may have
left a visible-only or other filtered view. Diff returns `RESET_REQUIRED` if
history is unavailable, query scope differs, or either endpoint is capped; even
an unchanged capped result cannot certify a complete diff. A fresh bounded snapshot
may itself remain capped and must not be mistaken for a complete enumeration.
Publishers use `metadata.queryScope` for all selection and authorization inputs;
other metadata may change and is included in the diff. Legacy publishers without
that object reset conservatively if any metadata changes. Malformed or duplicate
node identities are rejected without advancing history. Unchanged observations
retain their scene version. No periodic observer timer, subscription thread or full-desktop
polling is installed. A production bounded subscription API is a future contract,
not a fake success function.

Limits: 96 returned nodes/query (up to 128 visited for filtered Qt queries), depth 12 for Qt / 18 for admitted HTML, 128 retained
identities/publication maximum, 1024 text characters/node and 8192 total text
characters/query, 65536 encoded node bytes/publication, two retained snapshots.
Traversal stops after a checked 30ms monotonic budget between nodes and reports
capped; a single native method/serialization is not a hard real-time bound. Browser
fragment admission is ≤8 per element, with explicit completeness. Full hostile GUI
provider stress, allocator exhaustion and absolute query latency bounds are not
established by these finite tests.

## Typed actions and the separate local test adapter

SSG action descriptors (`inspect`, focus, set_text, activate, select, scroll) describe
capability intent; the Notes/Browser providers are **READ_ONLY**. Their cross-process
execution, wait_for_state and verify_result transport are **NOT_IMPLEMENTED / NOT_RUN**.
No consumer may execute a stale coordinate after document replacement.

`Semantics` is a deliberately smaller local Intent adapter for the independent
fixture. It registers only explicit target Widgets. A deterministic independent
host mock consumes the *actual guest SSG snapshot*, chooses an admitted textbox
and emits a proposal. The authorized test harness types that proposal into the
guest fixture and clicks its explicit local authorization button. This is not a
claim that an XOS AI process obtained an OS action lease.

The trusted host creates a move-only, one-shot Grant bound to the exact proposal,
target/state revision, local authorization epoch and monotonic expiry. No grant
is serialized to the model. Execute without grant, changed proposal, revoked,
expired, reused or dead/stale target refuses. Current local set_text verifies the
real resulting QLineEdit value. Button dispatch returns UNKNOWN because a signal
does not prove an external effect; that grant is consumed and cannot be replayed.
The test button causes no real external transaction. The host authorization call
is an adapter seam, not an implementation of user identity or a production policy
gateway. Those responsibilities cannot be delegated to a language model.

Future production sequence: authenticate observation scope → obtain bounded SSG
snapshot → propose typed action with stable reference and expected state → trusted
Permission Gateway authorizes exact operation/scope/expiry → application adapter
executes → independently observe verification conditions → issue a receipt.
External UNKNOWN stays UNKNOWN until reconciled; never automatically retry.

## Cross-process gap and comparison boundary

Current arbitrary peer endpoint creation/grants and multiwindow transport are
insufficient; see the separate [compositor gap proposal](aurora_compositor_proposal.md).
Do not repurpose file-service identity or add an AI syscall to bypass this gap.
A future userland aggregator needs separately reviewed authenticated service
discovery, attenuated observe/action leases, revocation/disconnect notifications,
queue/text/node/subscription quotas and browser-origin enforcement.

The comparison report records actual SSG bytes, a clearly labeled AX-style
projection of the same Qt metadata, controlled target selection success and
actual screenshot bytes/capture time. XOS has no newly qualified AX service, and
no XOS OCR engine is implemented. A separate host-only macOS Vision reference
reads a synthetic QEMU screenshot: its recognized link bounds are compared with
the actual SSG fragment. Cold host initialization time, processing context and
confidence are recorded; this is not a guest OCR port or a fair same-hardware
latency comparison. Therefore real AX versus SSG versus OCR universal success
rates or whole-desktop coverage cannot be claimed. These unknowns remain visible
rather than treating a projection or screenshot as a completed observation system.

Failure of a query should return DENIED/UNAVAILABLE/RESOURCE_LIMIT/capped; normal
mouse/keyboard rendering requires no AI. Notes/Browser lifecycle and functional
regressions on the affected combination are separate required gates. QEMU/serial
rescue and exact resource return are observed; physical hardware, SMP, long stress,
screen readers and whole-desktop security qualification remain separate work.
