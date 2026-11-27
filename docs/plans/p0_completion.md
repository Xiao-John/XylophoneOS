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
file SHA-256 entries. Before a commit, run the public-path check against
`origin/main` and verify every new evidence index. Public logs contain no local
operator paths or private fixture keys.

Module PRs report dependencies and never claim that unmerged code is mainline.
`docs/state.md` remains the integrator's merged/released milestone record. This
campaign's closure and next-round table are updated here after actual module
delivery. A remaining P0 requirement is retained as P0, not silently moved to
P1 to declare completion.

## P1 table to refresh after P0 delivery

| Workstream | Next-round outcome | Boundary to preserve |
| --- | --- | --- |
| ClarkE | Link the full WebCore platform; qualify DOM, CSS layout, rendering, Qt viewport and isolated renderer/network lifetimes. | A static archive or HTML tokenizer is not a working full page. |
| Mobius | Multiwindow composition, focus/input ownership and application interactions. | Current single-surface qualification is retained separately. |
| Pumpkin | Physical deployment, trusted generation provisioning and persistent user/resource authorization. | QEMU/developer identity and host process interruption do not prove physical power-loss recovery. |
| xypm | Trusted official repository metadata, dependency resolution and external application distribution. | Existing offline P2/P3 transactions remain useful; online trust and rollback freshness need their own acceptance. |
| Storage | Application data isolation and transactional recovery including interrupted writes/power loss. | Normal sync/reboot and host process interruption do not qualify arbitrary power failure. |
| AI-ready groundwork | Read-only typed state/intent interfaces and replayable evaluations using the P0 authority, budget and lifetime mechanisms. | Keep model execution and unrestricted autonomous control outside the OS release critical path, per C04/C11. |

The final table will add concrete deliverables, dependencies and acceptance
criteria derived from this campaign, and link the actual PRs and results.
