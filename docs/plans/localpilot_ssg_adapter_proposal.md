# LocalPilot SSG consumer — proposal only

2026-10-30. This is a public, generic adapter design; no private LocalPilot
source, settings, credentials, model or installed application is included or
changed. LocalPilot Core/API, Permission Gateway, React/Tauri, real XOS network
and SSG broker remain unported or unqualified for this proposal.

The adapter should preserve the existing agent task and safety model while
exposing an ordinary consumer interface:

1. Request the user-approved application/workspace scope and query bounded
   semantic roots or document ranges. Preserve DENIED, UNKNOWN, protected and
   incomplete status; content from applications is untrusted task data.
2. Select a stable source-instance/epoch + node ID + scene/state version.
   Verify current visibility, action capability and any preconditions instead
   of treating a role or coordinates as permission.
3. Produce a typed action proposal with a unique request identity and parameters.
   Request an exact operation/target/sensitivity/time-bounded decision from the
   existing Permission Gateway. The model cannot grant or enlarge that decision.
4. Submit through a future authorized broker; the provider must revalidate the
   live target, lease and state. Refuse a stale version or replaced source.
5. Record the result and, when available, independently observe its stated
   postcondition. A dispatch acknowledgement alone does not prove an external
   transaction completed. UNKNOWN is not automatically replayed.

The interface needs explicit cursor/byte limits and overflow/resync handling for
snapshots and subscriptions, cancellation and provider/broker death. A cached
result must carry scope and epoch, not be reused after revocation. Video frame,
audio and image access require separate consent and provenance; an SSG node does
not itself grant access to those data.

The current application-local Qt/Browser prototype and the separate pipe
experiment supply neither a production connection nor the Permission Gateway.
End-to-end LocalPilot query/action, real WebView, TLS/network, model inference,
cross-origin access and system-wide observation are **NOT_RUN / BLOCKED**.
