# Application-local SSG and regressions

Notes: live Qt tree, bounded document text, actual selection/scroll, read-only
queries, edit diffs and exact exit cleanup. Its initial whole-tree query may hit
the 30ms cap; document-role queries avoid unrelated controls. Text is a document
prefix (1024 chars/node, 8192/query), not a claim that all characters are visible.

Browser: real liteHTML/Gumbo element/text model, computed display, bounded actual
render fragments, viewport visibility, scrolling, actual engine click using SSG
link geometry, reload epoch invalidation, unsupported canvas rejection and cleanup.
No arbitrary DOM/iframe/Shadow DOM/forms/modern JavaScript support is claimed.
The small upstream patch is read-only; pristine source hashes/licenses remain intact.

Affected Notes gates pass: real editing/selection/save, long scrolling, unsaved
Cancel/Discard, BOM/CRLF/empty/no-EOL, new file, sync + reboot byte-exact readback,
three lifecycle cycles, kill/display loss/restart and no-display refusal.
Affected Browser gates pass: links/history/refresh/tabs/bookmarks/CSS/BMP, negative
content/admission/failing-layout recovery with preserved history/tab/scroll state,
normal/kill/display failure/restart and serial/file-service survival. All counters
return to their respective baselines. This closes the relevant previously unrun
merged PR19 candidate-navigation regression on these exact artifacts.

Both xsh and real dash launch the desktop/semantic SDK probes. The gap probe runs
under dash too; starting the session without delegated child-spawn authority fails
with real denial and status 1 rather than claiming success.

Comparison: the 8499-byte controlled SSG snapshot is compared with a deliberately
minimal 647-byte role/name/enabled projection and a real synthetic screenshot.
The projection is **not** a real AX service or an equivalent representation of all
AX attributes, so these sizes do not establish AX overhead or coverage superiority.
The independent mock locates 1/1 controlled target. A host-only macOS Vision OCR
reference locates the visible native-link line overlapping the real SSG fragment
(confidence output 1.0); first-request elapsed time is 62.54s with initialization/load contributions not isolated. It is not a guest OCR implementation or a fair same-environment
latency comparison. OCR action execution and a real XOS AX service remain NOT_RUN.

Cross-process observing/authorization/aggregation is BLOCKED: no such endpoint is
exposed. Existing display denial and address-space isolation are not rebranded as
a new whole-desktop SSG security qualification. Custom painting returns unavailable;
external compositor occlusion stays unknown. See the SSG contract and LP0 matrix.
