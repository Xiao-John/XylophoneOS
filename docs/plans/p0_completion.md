# P0 completion campaign

## Scope and baseline

The requested P0 work covers glibc distribution and dynamic application startup,
authority and process lifetimes, and usable network configuration and transport.
The starting commit is `daf2bd24ce92525ce61054ebe585ab0e88ed06e4`. Existing
implementations and frozen qualifications remain distinct from this campaign's
new results. A module is delivered through its own `codex/` branch and PR;
opening a PR does not merge it or publish a release.

Development uses the Linux x86-64 `xos-sdk-preview-2` release asset, SHA-256
`60df6913fe2a56517e645c93673ebd9590ba3dd90acc56030c80c3738955cac9`.
The bundled target sysroot is newlib. Its host cross tools build a separate,
signature-verified glibc SDK. The two target sysroots, application profiles and
rollback media must not be mixed. Every module uses its own worktree and build
directory. No shared build directory is cleaned or rebuilt concurrently.

The SDK launcher and bundled QEMU/TCG smoke passed during environment setup.
The launcher's optional `--offline` mode failed because this host rejects its
NETLINK_ROUTE socket. Normal launcher mode passed; that is not evidence of
network-namespace isolation. Build inputs are explicit locked archives.

## Modules and acceptance

| Module | Work | Required evidence and dependency |
| --- | --- | --- |
| P0-L1 | Deterministic IPC lifetime cancellation | Observe a waiter actually blocked before exec/revocation; require the contracted broken result, retain failed-exec authority, reject stale handles and reclaim resources. No timing-only substitute for the blocking precondition. |
| P0-L2 | Authority budgets and service restart | Reuse existing delegation, revocation and wait-any. Close any confirmed ownership/fairness gaps; test exhaustion isolation, independent service restart, stale reference rejection, and observable failure or unknown outcome without replaying uncertain operations. |
| P0-R1 | glibc release composition | One explicit glibc entry assembles the system, installer, SDK, packages and retained materials, verifies their identities and runs relevant gates. Missing input or a failed gate must stop promotion. Preserve an explicit frozen newlib path. |
| P0-R2 | Immutable dynamic generations | Verify the complete object closure, identities and bounded resources; stage immutable generations and implement authorized activation, revocation and recovery/rollback. A collection of independent package writes is not an atomic generation commit. |
| P0-R3 | Public dynamic startup and D3/D4 qualification | Extend ordinary user-space loader/startup with authenticated identity, ready/error and lifecycle semantics. Test real xsh/dash launch, exec, descriptors, failure and resource cleanup against the selected generation. Private D1/D2 fixtures and fixed closures do not qualify public runtime loading. Depends on R2 and rebuilt glibc/rtld inputs. |
| P0-N1 | Native socket readiness and half-close | Versioned capability discovery, level readiness and TCP write shutdown; retain old clients and enforce ownership/deadlines. Exercise real lwIP peers and negative paths. |
| P0-N2 | libc socket wait bridge | Bind socket readiness/shutdown to libc descriptors, absolute monotonic deadlines and errors. Validate timeout, EOF, cancellation, invalid descriptors and cleanup. State exactly which poll/nonblocking operations are supported. Depends on N1 and a matching glibc SDK. |
| P0-N3 | Deployed DNS and DHCP policy | Preserve existing resolver tickets and trusted static configuration; make address authority explicit, implement bounded DHCP lease/configuration lifecycle, and test renewal, expiry, rejection and service restart. A successful DNS lookup never creates connection authority. |
| P0-N4 | Versioned TLS trust stores | Replace the single embedded test-root limitation with bounded independently pinned CA snapshots, validated parsing and explicit update/rollback identity. Keep hostname, time, chain validation and authenticated TLS closure. Test authorized roots, removed/untrusted roots, corruption and invalid input with real TLS. |
| P0-I | Combined acceptance | Compose the delivered branches without changing frozen results. Run affected ordinary smoke, ABI, licensing and module gates against the actual combined tree and selected SDK. Record all failures and unrun requirements. R1 release promotion and R3 D3/D4 remain blocked until their actual full input sets pass. |

N1, L1 and R1 proceed independently. N2 follows N1. N4 can proceed alongside N3.
R2/R3 use explicit generation and ABI contracts and cannot be replaced by
removing existing dynamic-loader guards. Public ABI edits include caller,
authority, compatibility, error, lifetime and rollback documentation together
with headers, SDK and affected tests.

## PR and evidence discipline

Each module records the source baseline, SDK/archive identities, exact commands,
tested configuration, success/failure/not-run results and remaining scope in a
new work log. Reports use a flat `manifest.json` with `version: 1` and relative
file SHA-256 entries. After staging, run
`python3 tests/check_public_evidence_paths.py --index --base origin/main`
against the actual index and verify every new evidence index. Rerun the check
after any subsequent index change. Public logs contain no local operator paths
or private fixture keys.

Module PRs report dependencies and never claim that unmerged code is mainline.
`docs/state.md` remains the integrator's merged/released milestone record. This
campaign's closure and next-round table are updated here after actual module
delivery. A remaining P0 requirement is retained as P0, not silently moved to
P1 to declare completion.

## Public delivery checkpoint: 2026-11-28 Asia/Singapore

GitHub records PRs [#397](https://github.com/Xiao-John/XylophoneOS/pull/397)
through [#417](https://github.com/Xiao-John/XylophoneOS/pull/417), and
[#419](https://github.com/Xiao-John/XylophoneOS/pull/419), as merged.
The public integration merge is
`4444b9df1b82c2556d70363753305b55fd7a579d`.
This supersedes the old statement that the campaign PRs were still open.

The table below records the already-public implementation and contract scope.
Detailed final integration and network acceptance appendices remain withheld
after automatic publication review required specific authorization. Their
public-delivery gates remain P0 work. This roadmap contains public repository
status and future tasks; it does not reproduce those appendices or use an
unpublished report as a public citation. The restriction is recorded in
[#417](https://github.com/Xiao-John/XylophoneOS/pull/417) and
[#418](https://github.com/Xiao-John/XylophoneOS/pull/418), whose historical
network-evidence branch remains a draft.

### Merged implementation map

| Module | Public implementation PRs | Contract and remaining delivery boundary |
| --- | --- | --- |
| L1 | #400, #403, #415 | IPC lifetime, broken-wait behavior, failed-exec preservation, restart and finite deadlines. The final acceptance appendix is a separate delivery item. |
| L2 | #401, #403, #412, #415, #416 | Per-owner quotas and authenticated launch/READY/ACK control. Process-tree aggregation and persistent attribution are new capabilities. |
| R1 | #398, #402, #413, #417 | Explicit glibc release pipeline, reusable static C++ SDK recipe, source authentication, frozen-SDK rollback guards and receiver support. Final distribution qualification records require separate publication authorization. |
| R2 | #408, #415 | Immutable approved closures, activation, rollback and revocation under a bounded per-controller volatile catalog. Persistent provisioning and descendant-wide revocation are future work. |
| R3 | #406, #410, #415, #419 | Public GNU startup, Files deadlines, ordinary spawn/same-PID exec and child-owned stdio pipe routes. Online dynamic-library loading and dynamic fork-to-exec controller migration remain outside the public startup profile. |
| N1 | #399 | Native readiness and TCP write half-close, with ownership and deadlines. Physical NIC qualification is separate. |
| N2 | #407 | The finite libc poll/shutdown profile and descriptor leases. The existing thread contract returns ENOTSUP for pthread_cancel; successful cancellation delivery and simultaneous close/revoke-in-poll guest qualification are separate scope. |
| N3 | #405, #409, #414 | Trusted DHCP/ACD address lifecycle, sealed egress policy and DNS separation. A DNS result does not grant connection authority. |
| N4 | #404 | Bounded independently pinned CA stores and explicit update/rollback identity. This does not establish default installed networking, trusted time, hardware entropy or full browser policy. |
| I | #411, #417 | Bounded FIFO QMP and integration/SDK/release qualification support. Final integration and network evidence publication remains open; it is not moved into P1. |

The original acceptance requirements above remain unchanged. In particular,
the supported native session-abort operation and the explicitly unsupported
POSIX pthread-cancellation delivery have separate contracts; a native abort
must not be described as a pthread cancel. See the public
[Net2 contract](../contracts/net_service_v2.md),
[static-thread contract](../contracts/glibc_static_threads.md),
[DHCP profile](../contracts/dhcp_service_profile.md), and
[TLS trust-store contract](../contracts/tls_trust_store.md).

The original interrupted checkpoint remains in Git history and the
[interruption work log](../work_log/0c6fe827_p0_environment_interruption.md).
The public merge record above does not rewrite any historical test outcome.

## Updated P1 table: next-round delivery and acceptance

This table replaces the initial broad workstreams with concrete outcomes.
It preserves the original P0 acceptance requirements. New capability work can
start once its named technical prerequisites pass. Outstanding final integration
and network evidence publication remain P0 delivery items; they are not
reassigned here.

| Priority / workstream | Next-round deliverable | Entry dependency | Acceptance and retained boundary |
| --- | --- | --- | --- |
| P1-A / AI-ready observation | A versioned typed read-only state interface for processes, services, resources and active runtime/network/trust generations; a separate typed intent/proposal schema; recorded observations and replayable evaluation fixtures. | Integrated L1/L2, R2 and the relevant service snapshots. | Authorized reads succeed; unauthorized/stale handles, service restart, revocation, deadline and quota exhaustion return typed observable outcomes. Offline replay of the same recorded observation/proposal pair with the recorded schema, validator/policy version and logical-time inputs produces the same validation result; model output is recorded, not assumed deterministic. An intent is a proposal, not execution authority. No model or autonomous controller becomes an OS release dependency (C04/C11). |
| P1-B / authority and lifetime | Process-tree cumulative budgets/delegation, resource attribution, observable quarantine for uncertain Files results, and a controller concurrency contract. | Existing per-PID quotas, absolute deadlines, public wait and loader cleanup. | Forking cannot multiply a delegated tree budget; unrelated owners remain usable; exit/restart returns credits. Real guest fault injection covers uncertain OPEN/CLOSE without replay. Existing READY/ACK, same-pin loading and failed-activation rollback remain completed prerequisites, not new gaps. |
| P1-C / Pumpkin provisioning | Persisted approved generation/catalog provisioning, restart recovery, persistent user/resource authorization and an explicit revocation model across descendants. | Completed R1/R2/R3 and their final installation artifacts. | Cold restart retains the approved active root or deterministically recovers an authorized prior root; stale/unapproved roots cannot self-authorize. Physical deployment and power-failure injection receive separate evidence. A volatile user-space grant-to-commit protocol does not imply instantaneous global revocation. |
| P1-D / xypm distribution | Authenticated official repository metadata, freshness/rollback policy, bounded dependency resolution and external-application installation through approved generation staging. | R1 material/source correspondence and R2 complete-closure activation. | Reject altered/expired/rollback metadata, conflicting or cyclic dependencies and missing objects before activation; interrupted staging keeps the previous generation usable. Downloaded metadata and successful DNS resolution do not grant execution/network authority. |
| P1-E / Storage and application data | Explicit per-application data authority plus recoverable transactions for application data and installation metadata. | Files lifetimes/deadlines and the generation activation contract. | Cross-application access is denied; interrupted writes and metadata transitions expose a documented old/new/recovery state; fault injection checks actual recovery. Normal sync/reboot and host process interruption alone do not qualify arbitrary power loss. |
| P1-F / ClarkE | Full WebCore integration with a rendered DOM/CSS fixture set, Qt viewport and isolated renderer/network lifetimes. | Usable C++ runtime, Files, TLS/network APIs and bounded process startup. | Real WebCore performs layout and painting for an explicit feature set; navigation/cancel/renderer failure releases resources and applies network policy. Static archives and tokenizers are not a full-page browser. |
| P1-G / Mobius | Multiple visible application windows, composition/damage handling, focus and input ownership, resize/close and application-failure recovery. | Current display/input ABI and process/resource lifecycle. | Two independent applications render and receive only their owned input; focus changes, resize and one application crashing preserve the other application's window and resources. Keep previous single-surface qualification separate. |
| P1-H / network readiness | Add a fresh-state/notification mechanism for connected-socket poll(0), then qualify nonblocking connect, further descriptor types and shutdown directions explicitly. | Completed N1/N2 and matching final SDK. | Already-ready sockets return promptly; an unknown or stale state cannot be reported as not ready. FIN, write-window changes, late replies and a live but unresponsive service stay within the caller's deadline. Each new capability has real-peer positive/negative and ownership tests. A separate real guest must observe poll pending while another thread closes or revokes the original socket, then verify open-description identity, bounded error, late replies, unrelated FD usability and resource recovery. pthread_cancel remains ENOTSUP until a new cancellation-delivery capability is specified and qualified. |
| P1-I / resolver and link recovery | Controlled multiple-resolver failover, followed by link-loss/device-reappearance recovery and physical NIC qualification as separate modules. | Completed N3, current one-active-resolver/direct-Ethernet IPv4 profile. | Resolver failover shares one deadline; TTL/cancel/quota tests pass; epoch changes retire old caches/tickets. Link loss revokes usability, recovery reacquires and performs ACD; old connections and queued ARP data do not revive. Virtual NIC results do not establish physical NIC qualification. |
| P1-J / repeatable distribution | Automate the R1 receiver/source/relink/guest/freeze workflow in independent clean build runs after its first qualification is accepted. | Use the completed and approved first R1 qualification as an entry gate. | At least two independently recorded runs bind tools, source, SDK, packages and media consistently; wrong hashes, stale SDKs and missing source stop publication. Automation cannot replace the first R1 qualification and its required delivery gates. |
| P1-K1 / libc timed waits | Implement nanosleep and clock_nanosleep with relative/absolute monotonic deadlines, interruption and remaining-time semantics. | Existing monotonic clock, finite poll and IPC deadlines. | Specify the supported interruption mechanism first; current pthread_cancel delivery is unavailable. Real target tests cover normal wake, an expired deadline, the new interruption mechanism and bounded late replies. Current GNU ENOSYS stubs are explicit; sched_yield-based constructor tests do not qualify sleep APIs. |
| P1-K2 / dynamic process composition | Specify and implement parent-controller ownership migration for dynamic fork-to-exec and the separate terminal-actor dynamic exec protocol. | Completed ordinary public spawn/exec and authenticated READY/ACK. | Actual fork/exec/terminal-owner death cases preserve authority, PID/FD rules and cleanup; a console or Files stdio result is not used as terminal-actor evidence. Split the two protocols into separate PRs. |
| P1-K3 / online dynamic libraries | Define approved online dlopen/dlmopen/dlclose with namespace, dependency/refcount, TLS, destructor and unload lifetimes. | Startup-only approved closures and same-pin identity validation. | New/missing/wrong-version objects fail before use; real concurrent threads, TLS destructors and unload pin lifetimes are tested. Existing explicit denial stays in force until the new profile qualifies. |
| P1-K4 / installed-profile composition | Qualify default installation networking and dynamic GNU applications with the explicit DHCP/TLS profiles as named combined configurations. | Completed individual R3 and N1–N4 configurations. | Bind the installed image, bootstrap network profile, caller SDK/runtime, lease authority and trust generation. Cold-boot the actual selected installation, renew/expire/restart services and verify dynamic callers' bounded failures and recovery. Controlled manual service startup and separate static/DHCP reports do not establish this installed combination. |
| P1-K5 / independent pipe transfer | Extend the current fixed stdio transport to explicitly authorized independent pipe-object transfer, with bounded capacity and atomic failure cleanup. | Completed v3 child-route fix, SDK archive pipe regression and real GNU dynamic pipe execution. | Preserve shared aliases, CLOEXEC, direction, EOF/EPIPE and parent ownership through spawn/exec. The current 32-FD snapshot limit includes aliases and Files descriptors; it does not promise 32 independent pipe objects. Ordinary spawn continues to reject unrouted independent pipe objects; the existing same-PID exec handle-preservation path remains unchanged. |

P1-H/I extend coverage. Existing DHCP expiry, TCP write half-close, egress/DNS
separation and bounded CA snapshots remain established module results; the
remaining detailed qualification publication is still P0-I.

The first AI-ready module should be P1-A: a useful, testable observation and
proposal boundary. Writing actions require their own explicit authority,
preconditions, result/unknown-result semantics, budgets and replay prohibition.
Those contracts must be reviewed and tested before adding autonomous write
operations; a natural-language command alone is not a capability.

## Next implementation sequence

1. Resolve the outstanding specific authorization for final qualification
   appendices and finish their P0 public-delivery gates.
2. Begin P1-A with a bounded versioned read-only observation endpoint, typed
   proposals and offline replay fixtures. An ordinary client must exercise the
   interface without a model or an autonomous writer.
3. Implement P1-B and the relevant P1-C/E authorization and recovery contracts
   before granting persistent write actions to an AI consumer. Unknown outcomes
   require reconciliation and must not be replayed automatically.
4. Prioritize P1-K1 and the necessary K2/K4 runtime combinations for application
   consumers. Keep independent pipe transfer and online library loading under
   their own explicit profiles and PRs.
5. Advance authenticated distribution, WebCore, multiple-window composition
   and repeatable builds against those interfaces, with separate acceptance.

### AI-ready staging decision

The merged authority, lifecycle and public-runtime interfaces provide an entry
point for the read-only observation and proposal phase. The first deliverable
is a versioned interface and a reproducible validation fixture. Model output
is recorded as input to validation; it does not become an authorization token,
a trusted kernel component, or an OS release dependency. Autonomous persistent
writes require the separate budget, authorization and recovery work above.

### P1-A delivery checkpoint: 2026-11-28 Asia/Shanghai

The read-only observation/proposal boundary is implemented and qualified in
the profiles recorded by the [P1-A delivery log](../work_log/63c043b9_p1_a_observation.md)
and [qualification](../reports/p1_a_observation_20261128/qualification.json).
It includes bounded scoped sys90 reads, authenticated user-space grants tied to
PID/image generation, six typed source adapters, separate proposal schemas and
deterministic offline evaluation. Ordinary native clients pass 21 guest cases;
live static Net2 passes three rounds; real loaded-trust snapshots pass 45 guest
checks; the affected IPC lifecycle suite passes four cases. All 102 actual
observation/proposal recordings replay identically.

Runtime observations describe a local volatile catalog. Trust observations
describe the owner's selected, successfully loaded CA snapshot through an
optional native TLS bridge, without changing existing streams. The default
consumer is not an installed inventory daemon, and separately sampled records
are not a global atomic snapshot. A proposal remains non-executable and all
verdicts prohibit automatic retry. Persistent authority, tree budgets and
recoverable writes remain P1-B and the relevant P1-C/E work. This checkpoint
does not change the outstanding P0 acceptance or public-delivery requirements.
