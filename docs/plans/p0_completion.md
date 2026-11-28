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

## Public delivery checkpoint: 2026-11-28 Asia/Shanghai

The implementation campaign (#397–#417 and #419) is merged. This follow-up
rebuilt and reran the P0 acceptance in the checksum-pinned SDK environment,
published fresh minimal evidence per module, and retained each result's actual
source, SDK, image and configuration identities. Different qualified profiles
are not relabelled as one identical system.

**Publication status: SDK prerelease published and verified; R1 hosted-asset delivery pending.**
The [final delivery receipt](../releases/p0_glibc_preview_3_delivery.json) records
the observed SDK tag, successful recovery workflow and five public-download
digests. R1 upload and its hosted-asset verification remain pending.
The new [glibc host SDK](../releases/glibc_host_sdk.md) defaults to static glibc
C/C++; the R1 distribution has a separate, explicitly bound application profile.
Use the matching R1 kit for its disk and packages.

### Completed implementation and fresh acceptance

| Module | Implementation PRs | Fresh delivery PRs / evidence | Qualified result and retained boundary |
| --- | --- | --- | --- |
| L1 / L2 | #400, #401, #403, #412, #415, #416 | [#432](https://github.com/Xiao-John/XylophoneOS/pull/432), [native integration](../reports/p0_integration_final_20261128/README.md) | 33 launch checks; 12 IPC lifetime/authority/quota mode runs; 3 deadline rounds covering 6 conditions each; 45 stdio checks over 12 native target executions. Resource baselines and user data return. Process-tree budgets and persistent attribution remain new capabilities. |
| R1 | #398, #402, #413, #417 | [#435](https://github.com/Xiao-John/XylophoneOS/pull/435), [final distribution](../reports/p0_release_final_20261128/README.md), [work log](../work_log/90c2ce10_p0_r1_final_distribution.md) | Exact system, installer, SDK/profile, packages and materials are bound together. Five detached receivers reproduce 17 original glibc programs byte for byte; one-member libc replacement is exercised in the real guest. Package lifecycle, native GNU C/C++/Make/Python composition, interrupted upgrade/recovery, and frozen-newlib roundtrip pass. Outer asset publication is separately recorded in the delivery receipt. |
| R2 | #408, #415 | [#429](https://github.com/Xiao-John/XylophoneOS/pull/429), [generation evidence](../reports/p0_generation_closure_20261128/README.md) | 21 checks in 3 rounds with 12 actual GNU launches; 23 ordinary and 23 ASan/UBSan host checks. Activation, old pins, stale sequence rejection, failed candidate preservation, rollback and revocation pass within the bounded volatile controller catalog. |
| R3 | #406, #410, #415, #419 | [#430](https://github.com/Xiao-John/XylophoneOS/pull/430), [public runtime](../reports/p0_public_runtime_closure_20261128/README.md) | All 9 public GNU startup cases pass: C policy/spawn/exec/pipe plus C++ and threads through xsh/dash. Cross-object exceptions, RTTI, unwind, TLS destructors and cleanup use the authenticated startup closure. Online library loading and dynamic fork-to-exec controller migration remain outside this profile. |
| N1 | #399 | [#426](https://github.com/Xiao-John/XylophoneOS/pull/426), [native network](../reports/p0_n1_final_20261128/README.md) | 12 real-peer guest cases; 32 lwIP and 2 service-loop sanitizer cases. Readiness, write half-close, zero-window queued close, EOF order, ownership, deadlines and resource return pass. Physical NIC qualification is separate. |
| N2 | #407 | [#425](https://github.com/Xiao-John/XylophoneOS/pull/425), [glibc socket bridge](../reports/p0_n2_final_20261128/README.md) | 12 actual glibc TCP/poll/shutdown cases, including absent/wrong service, descriptor bounds, a finite deadline and late-peer recovery. Connected poll(0), simultaneous close/revoke during poll and successful pthread cancellation remain separate capabilities. |
| N3 | #405, #409, #414 | [#424](https://github.com/Xiao-John/XylophoneOS/pull/424), [DHCP evidence](../reports/p0_n3_final_20261128/README.md) | 8 DHCP/ACD peer scenarios cover renewal, expiry, NAK, new issuer, malformed input, conflict/backoff and service restart; 18 sanitizer, 24 JSON rejection and 27 egress host cases pass. DNS resolution does not grant connection authority. |
| N4 | #404 | [#427](https://github.com/Xiao-John/XylophoneOS/pull/427), [TLS evidence](../reports/p0_n4_final_20261128/README.md) | 20 real TLS/trust cases, 15 target parser cases, 118 pinned CA roots parsed and 24 packer checks. Unauthorized certificates send no application request; absent entropy fails closed. Trusted production time, hardware entropy, OCSP/CRL and installed default networking remain separate. |
| Packaged SDK pipe | #419 | [#428](https://github.com/Xiao-John/XylophoneOS/pull/428), [SDK archive regression](../reports/p0_sdk_pipe_closure_20261128/README.md) | 4 cases launch 4 actual children through the packaged libxos_terminal.a, without replacing the loader implementation. Additional independent pipe-object transfer is separate scope. |
| I / distribution support | #411, #417 | [#422](https://github.com/Xiao-John/XylophoneOS/pull/422), [#423](https://github.com/Xiao-John/XylophoneOS/pull/423), [#431](https://github.com/Xiao-John/XylophoneOS/pull/431), [#432](https://github.com/Xiao-John/XylophoneOS/pull/432), [#433](https://github.com/Xiao-John/XylophoneOS/pull/433), [#436](https://github.com/Xiao-John/XylophoneOS/pull/436) | Final R1 native candidate 7c8c59058be0b5f1 passes 79 ordinary checks, 10 license-material checks and ABI consistency. Fixed the pinned zlib URL and its ledger digest. The new host-SDK recipe binds committed source, freshly extracts the finished archive and runs its packaged C/C++ programs before publication. |

The original acceptance requirements above remain unchanged. The supported
native session-abort operation and unsupported POSIX pthread-cancellation
have separate contracts; a native abort is not pthread_cancel. See the
[Net2 contract](../contracts/net_service_v2.md),
[static-thread contract](../contracts/glibc_static_threads.md),
[DHCP profile](../contracts/dhcp_service_profile.md), and
[TLS trust-store contract](../contracts/tls_trust_store.md).

Historical draft [#418](https://github.com/Xiao-John/XylophoneOS/pull/418) remains
a record of its earlier source and publication review. The refused historical
appendices were not republished. The fresh minimal reports above are new runs,
with explicit raw-report digest provenance and individual public PRs. The
[interruption work log](../work_log/0c6fe827_p0_environment_interruption.md)
and prior failures remain in history; their outcomes are not rewritten.

## Updated P1 table: next-round delivery and acceptance

This table replaces the initial broad workstreams with concrete outcomes.
It preserves the original P0 acceptance requirements. New capability work can
start once its named technical prerequisites pass. Fresh final integration and
network evidence are now public through the module PRs above. The SDK and R1
hosted-delivery gate is tracked separately until its actual upload is verified.

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
new capabilities remain in their named P1 entries; the fresh P0 qualification
reports above retain the exact tested limits.

P1-A provides the first AI-ready module: a scoped, qualified observation and
proposal boundary recorded in the delivery checkpoint below. Writing actions
require their own explicit authority, preconditions, result/unknown-result
semantics, budgets and replay prohibition.
Those contracts must be reviewed and tested before adding autonomous write
operations; a natural-language command alone is not a capability.

## Next implementation sequence

1. Preserve the qualified P0 release, profiles, materials and replay commands;
   finish and verify the hosted SDK/R1 delivery receipt before marking delivery closed.
2. Build ordinary consumers on the bounded read-only observation/proposal
   interface delivered in [#434](https://github.com/Xiao-John/XylophoneOS/pull/434).
   Its versioned endpoint, ordinary clients and offline replay are qualified
   within the profiles recorded below, without a model or an autonomous writer.
3. Implement P1-B and the relevant P1-C/E authorization and recovery contracts
   before granting persistent write actions to an AI consumer. Unknown outcomes
   require reconciliation and must not be replayed automatically.
4. Prioritize P1-K1 and the necessary K2/K4 runtime combinations for application
   consumers. Keep independent pipe transfer and online library loading under
   their own explicit profiles and PRs.
5. Advance authenticated distribution, WebCore, multiple-window composition
   and repeatable builds against those interfaces, with separate acceptance.

### AI-ready staging decision

The merged authority, lifecycle and public-runtime interfaces support the
qualified P1-A read-only observation and proposal phase. Its versioned interface
and reproducible validation fixtures provide the entry point for ordinary
consumers. Model output is recorded as input to validation; it does not become
an authorization token, a trusted kernel component, or an OS release dependency.
Autonomous persistent writes require the separate budget, authorization and
recovery work above.

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
