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

## Delivery checkpoint: 2026-11-28 Asia/Singapore

This is an interrupted implementation checkpoint, not campaign closure. GitHub
was re-read after the execution environment became unavailable. PRs
[#397](https://github.com/Xiao-John/XylophoneOS/pull/397) through
[#411](https://github.com/Xiao-John/XylophoneOS/pull/411) are open. They comprise
this plan and fourteen implementation or validation PRs. Main remains
`daf2bd24ce92525ce61054ebe585ab0e88ed06e4`. No campaign PR was merged and no release was
published. UTC-dated report directories retain their original dates.

The environment reported no usable execution environment, so pending local
commits, uncommitted changes and build outputs cannot currently be read or
published. The descriptions below distinguish remotely delivered modules from
the last successful local observations. A local commit/hash is not a remote
backup; recovery of the original workspace must be verified before continuing.

### P0 status and remaining gates

| Module | Delivered or observed result | Remaining P0 work |
| --- | --- | --- |
| L1 | [#400](https://github.com/Xiao-John/XylophoneOS/pull/400): genuinely blocked waiters, strict broken-channel result, failed-exec preservation, authenticated restart and reclamation. | Re-run affected cases on the final integrated source. |
| L2 | [#401](https://github.com/Xiao-John/XylophoneOS/pull/401): per-owner endpoint/name budgets. [#403](https://github.com/Xiao-John/XylophoneOS/pull/403): absolute IPC deadlines. Actual native launch-control READY/ACK and public wait pumping passed 33 local runs. | Publish the reviewed launch-control module and combine its actual quota/lifetime behavior with the public loader. Per-PID limits are not process-tree budgets. |
| R1 | [#398](https://github.com/Xiao-John/XylophoneOS/pull/398): explicit glibc release assembly/gates/atomic freeze and newlib selection. [#402](https://github.com/Xiao-John/XylophoneOS/pull/402): GCC authentication refresh with unchanged signer pins. A newly built static C++ SDK passed 11 local detached-consumer/system runs. | Publish the reusable C++ recipe, build a new SDK from final integrated source, run actual release composition, receiver relinks, package/installer gates, v6 material freeze, and glibc/frozen-newlib/glibc cold-boot rollback with preserved work data. The pipeline's host tests do not close R1. |
| R2 | [#408](https://github.com/Xiao-John/XylophoneOS/pull/408): native identities, bounded manifest graph and captured catalog. Subsequent local production code passed complete same-pin ELF closure preflight, failed activation retaining the old generation, authorized rollback/revocation, and 15 real GNU launches over three rounds. | Publish the complete public closure/activation module and run its gates in the combined tree. The qualified activation scope is one controller's volatile catalog; persistent recovery and stronger cross-descendant revocation remain distinct P1 work. |
| R3 | [#406](https://github.com/Xiao-John/XylophoneOS/pull/406): authenticated GNU rtld/libc/PIC CRT rebuild. [#410](https://github.com/Xiao-John/XylophoneOS/pull/410): native Files deadlines through the shared libc session. Local final C public startup/exec passed seven real scenarios. | Public C++ execution, real xsh and dash entry paths, explicit dlopen/dlmopen/dlclose profile behavior, a complete approved SDK-tree anchor for the installable launcher, final evidence and PR remain incomplete. D3/D4 are not qualified as a whole. |
| N1 | [#399](https://github.com/Xiao-John/XylophoneOS/pull/399): versioned native readiness and TCP write half-close, actual lwIP peer/FIN checks. | Final combined-tree regression. |
| N2 | [#407](https://github.com/Xiao-John/XylophoneOS/pull/407): libc poll/shutdown, descriptor leases and one absolute deadline across locks/IPC. Real guest and matching-kernel checks passed. | Rebuild and qualify the final glibc SDK with both network and public-loader changes. Preserve documented partial poll/nonblocking coverage. |
| N3 | [#405](https://github.com/Xiao-John/XylophoneOS/pull/405): strict DHCP parsing and lease-clock helper. [#409](https://github.com/Xiao-John/XylophoneOS/pull/409): sealed egress rules independent of DNS. Actual DHCP production integration subsequently passed seven local real guest scenarios. | Publish the actual DHCP integration; verify final DHCP-mode service restart, old-session retirement and network regressions in the combined tree. The helper PR alone is not an operational DHCP service. |
| N4 | [#404](https://github.com/Xiao-John/XylophoneOS/pull/404): bounded independently pinned CA stores, parsing, authorized update/rollback and real TLS negative paths. | Combined-tree regression and the final distribution's actual source/binary binding. Parsing a public CA bundle does not qualify general browser certificate policy. |
| I | [#411](https://github.com/Xiao-John/XylophoneOS/pull/411): actual QMP via private bounded FIFO transport in this environment. Intermediate combined Files/IPC/deadline gates passed. | Full final source build, ordinary smoke, ABI, licensing, all affected module/application gates and recorded release validation. No complete final smoke result was obtained before the environment interruption. |

The initial integration smoke also found that the repository pinned QEMU
11.1.2 while the verified Preview 2 SDK contains 11.1.3 with a Debian package
suffix. A local version-lock update and exact-version/suffix validation change
were prepared. The associated rebuild/smoke was not collected to completion;
this is not a successful qualification or a reason to ignore the lock.

### Published PR map

Dependencies are review bases, not an instruction to merge automatically.

| PR | Module | PR base |
| --- | --- | --- |
| [#398](https://github.com/Xiao-John/XylophoneOS/pull/398) | glibc release pipeline | main |
| [#399](https://github.com/Xiao-John/XylophoneOS/pull/399) | native network readiness/half-close | main |
| [#400](https://github.com/Xiao-John/XylophoneOS/pull/400) | IPC lifecycle/restart qualification | main |
| [#401](https://github.com/Xiao-John/XylophoneOS/pull/401) | owner quotas | #400 |
| [#402](https://github.com/Xiao-John/XylophoneOS/pull/402) | GCC source authentication | #398 |
| [#403](https://github.com/Xiao-John/XylophoneOS/pull/403) | absolute IPC deadlines | #400 |
| [#404](https://github.com/Xiao-John/XylophoneOS/pull/404) | TLS CA snapshots | main |
| [#405](https://github.com/Xiao-John/XylophoneOS/pull/405) | DHCP authority/lease helper | main |
| [#406](https://github.com/Xiao-John/XylophoneOS/pull/406) | reproducible shared GNU runtime | #402 |
| [#407](https://github.com/Xiao-John/XylophoneOS/pull/407) | glibc poll/shutdown | #399; also needs #403 for native deadlines |
| [#408](https://github.com/Xiao-John/XylophoneOS/pull/408) | native identity/generation admission | #406 |
| [#409](https://github.com/Xiao-John/XylophoneOS/pull/409) | trusted egress and DNS separation | #399 |
| [#410](https://github.com/Xiao-John/XylophoneOS/pull/410) | native Files deadline bridge | #408 |
| [#411](https://github.com/Xiao-John/XylophoneOS/pull/411) | real QMP FIFO transport | main |

Local module identities, successful runs and exact continuation points are
recorded in the
[interruption handoff](../work_log/0c6fe827_p0_environment_interruption.md).
Recover and inspect the existing workspace before replacing any worktree or
rebuilding inputs. Do not reconstruct uncommitted implementation from this
summary and label it as the previously tested tree.

## Updated P1 table: next-round delivery and acceptance

This table replaces the initial broad workstreams with concrete outcomes.
It does not reclassify unfinished R1/R3/integration work. Implementation can
be planned in parallel; qualification and release use must wait for the
corresponding P0 dependencies.

| Priority / workstream | Next-round deliverable | Entry dependency | Acceptance and retained boundary |
| --- | --- | --- | --- |
| P1-A / AI-ready observation | A versioned typed read-only state interface for processes, services, resources and active runtime/network/trust generations; a separate typed intent/proposal schema; recorded observations and replayable evaluation fixtures. | Integrated L1/L2, R2 and the relevant service snapshots. | Authorized reads succeed; unauthorized/stale handles, service restart, revocation, deadline and quota exhaustion return typed observable outcomes. Replay produces the same validated proposal from the same recorded inputs. An intent is a proposal, not execution authority. No model or autonomous controller becomes an OS release dependency (C04/C11). |
| P1-B / authority and lifetime | Process-tree cumulative budgets/delegation, resource attribution, observable quarantine for uncertain Files results, and a controller concurrency contract. | Existing per-PID quotas, absolute deadlines, public wait and loader cleanup. | Forking cannot multiply a delegated tree budget; unrelated owners remain usable; exit/restart returns credits. Real guest fault injection covers uncertain OPEN/CLOSE without replay. Existing READY/ACK, same-pin loading and failed-activation rollback remain completed prerequisites, not new gaps. |
| P1-C / Pumpkin provisioning | Persisted approved generation/catalog provisioning, restart recovery, persistent user/resource authorization and an explicit revocation model across descendants. | Completed R1/R2/R3 and their final installation artifacts. | Cold restart retains the approved active root or deterministically recovers an authorized prior root; stale/unapproved roots cannot self-authorize. Physical deployment and power-failure injection receive separate evidence. A volatile user-space grant-to-commit protocol does not imply instantaneous global revocation. |
| P1-D / xypm distribution | Authenticated official repository metadata, freshness/rollback policy, bounded dependency resolution and external-application installation through approved generation staging. | R1 material/source correspondence and R2 complete-closure activation. | Reject altered/expired/rollback metadata, conflicting or cyclic dependencies and missing objects before activation; interrupted staging keeps the previous generation usable. Downloaded metadata and successful DNS resolution do not grant execution/network authority. |
| P1-E / Storage and application data | Explicit per-application data authority plus recoverable transactions for application data and installation metadata. | Files lifetimes/deadlines and the generation activation contract. | Cross-application access is denied; interrupted writes and metadata transitions expose a documented old/new/recovery state; fault injection checks actual recovery. Normal sync/reboot and host process interruption alone do not qualify arbitrary power loss. |
| P1-F / ClarkE | Full WebCore integration with a rendered DOM/CSS fixture set, Qt viewport and isolated renderer/network lifetimes. | Usable C++ runtime, Files, TLS/network APIs and bounded process startup. | Real WebCore performs layout and painting for an explicit feature set; navigation/cancel/renderer failure releases resources and applies network policy. Static archives and tokenizers are not a full-page browser. |
| P1-G / Mobius | Multiple visible application windows, composition/damage handling, focus and input ownership, resize/close and application-failure recovery. | Current display/input ABI and process/resource lifecycle. | Two independent applications render and receive only their owned input; focus changes, resize and one application crashing preserve the other application's window and resources. Keep previous single-surface qualification separate. |
| P1-H / network readiness | Add a fresh-state/notification mechanism for connected-socket poll(0), then qualify nonblocking connect, further descriptor types and shutdown directions explicitly. | Completed N1/N2 and matching final SDK. | Already-ready sockets return promptly; an unknown or stale state cannot be reported as not ready. FIN, write-window changes, late replies and a live but unresponsive service stay within the caller's deadline. Each new capability has real-peer positive/negative and ownership tests. |
| P1-I / resolver and link recovery | Controlled multiple-resolver failover, followed by link-loss/device-reappearance recovery and physical NIC qualification as separate modules. | Completed N3, current one-active-resolver/direct-Ethernet IPv4 profile. | Resolver failover shares one deadline; TTL/cancel/quota tests pass; epoch changes retire old caches/tickets. Link loss revokes usability, recovery reacquires and performs ACD; old connections and queued ARP data do not revive. Virtual NIC results do not establish physical NIC qualification. |
| P1-J / repeatable distribution | Automate the already completed R1 receiver/source/relink/guest/freeze workflow in independent clean build runs. | The first full R1 closure must already have passed. | At least two independently recorded runs bind tools, source, SDK, packages and media consistently; wrong hashes, stale SDKs and missing source stop publication. This is continued automation, not a substitute for the pending first R1 run. |

P1-H/I extend coverage. Existing DHCP expiry, TCP write half-close, egress/DNS
separation and bounded CA snapshots remain established module results; the
final combined qualification is still P0-I.

The first AI-ready module should be P1-A: a useful, testable observation and
proposal boundary. Writing actions require their own explicit authority,
preconditions, result/unknown-result semantics, budgets and replay prohibition.
Those contracts must be reviewed and tested before adding autonomous write
operations; a natural-language command alone is not a capability.

## Immediate continuation order

1. Recover the original workspace and inspect all worktrees, pending source
   changes and raw reports. Preserve the completed local launch-control/DHCP
   commits and uncommitted runtime/C++ work before cleaning any intermediates.
2. Publish each complete reviewed module separately, with its existing evidence
   and exact tree equality checked. A failed or unconfirmed upload does not
   count as a PR.
3. Close remaining public-runtime gates: complete SDK-tree admission for the
   installable launcher, C++ execution, both shell entry paths and the explicit
   runtime dynamic-loading API contract. Rebuild any runtime changed by fixes
   and rerun the affected qualifications.
4. Compose final source and run I, then build one final C/C++ application SDK.
   Preserve first-link logs and object trees needed by source/relink collectors.
5. Perform the actual R1 distribution, relink/receiver/guest/materials gates and
   explicit frozen-newlib rollback. Do not publish a release as part of this
   campaign unless separately instructed.
6. Update the table from actual PR and qualification results. Close P0 only
   after its outstanding gates pass; then promote P1-A and the selected
   application/platform work into the next implementation round.
