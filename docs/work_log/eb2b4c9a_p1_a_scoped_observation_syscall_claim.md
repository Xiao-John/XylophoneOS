# P1-A scoped observation syscall claim

Baseline: `7d4489df05b5e6bff57794773d3f4a1727d8cc57`.
This registration-only change claims syscall 90 as `sys_observe` v1 under the
existing reserved system-foundation range. It adds no source constant, dispatch,
SDK capability or runtime implementation. The implementation branch is
`codex/p1-a-observation`; its implementation PR follows this claim's merge.

## Mechanism gap and boundary

Source inspection finds that `sys_process_stats` (21) exposes only global page,
task and completion counts. The legacy `sys_tasklist` (9) emits bounded text,
without a scoped, versioned process identity or image generation. Neither offers
typed self/direct-owned-child resource state and held-endpoint state with a
single absolute deadline. `sys_process_cpu_time` (89) remains its separate
self/current-thread accounting interface.

The proposed general mechanism reads only a kernel-authorized subject: the
calling process, a directly owned child, or an endpoint reference actually held
by the caller. It does not grant observation by a supplied PID/name alone,
enumerate unrelated owners, change rights, or perform an action. Kernel state
and lifetime validation are necessary at the observation point; parsing legacy
task-list text or self-reported service descriptions cannot supply them.

The user-space observation service reuses existing authenticated IPC. Runtime,
network and trust selection, policy validation and typed proposals remain in
user space. There is no AI-specific kernel policy or model dependency.

## Planned interface and ownership

The implementation will specify fixed-width v1 structures with exact version,
size and zero-reserved-field checks; scoped process/endpoint identity including
image/lifetime generation; a system-monotonic absolute deadline; and typed
denied, stale, timeout, unsupported and resource outcomes. It will initialize
failure outputs and reject unrecognized inputs. Old images without this
mechanism remain unsupported; callers must not fall back to broad task-list
parsing or report an empty successful snapshot.

The P1-A owner coordinates `src/shared/include/xos/observation_abi.hpp`,
`src/kernel/arch/x86_64/tasks.cpp`, the necessary process-record declaration,
`src/user/include/xos/sdk.hpp`, `scripts/build.py`, `scripts/user_build.py`,
`scripts/build_threading_sdk.py`, `docs/e04_loader_sdk.md`, the dedicated
observation contract and focused host/guest probes. The implementation PR will
move 90 from claimed to allocated, split the reserved range, and synchronize
both SDK manifests with explicit runtime qualification status. Existing syscall
layouts and meanings remain unchanged.

## Verification and continuation

`python3 tests/abi_doc_consistency.py --output-dir build/p1_a_claim` passed.
The live-link and registry functions from `tests/docs_consistency.py` passed;
the allocated syscall count remains 78. The complete command
`python3 tests/docs_consistency.py --output-dir build/p1_a_claim` stopped in
the unchanged historical-provenance stage: this checkout cannot read
`docs/work_log/0023_first_release.md` at source-index commit
`a265061ee00b787287011e5939054ebe3da4e397`. That full check is not claimed
as passed. Runtime tests are not applicable to this registration-only change;
no guest result, SDK qualification or P1-A completion is claimed.

`python3 tests/check_public_evidence_paths.py --index --base origin/main`
returned `PUBLIC_READY`: both changed documentation files scanned, no findings.
The check was repeated after the final index update.

After the claim merges, implement and qualify the narrow mechanism, IPC client
and service, provider adapters and deterministic offline proposal validation.
The P0 integration/network evidence-delivery gates remain separate.
