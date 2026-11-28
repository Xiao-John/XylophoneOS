# P0 L1/L2: final integrated native qualification

All three native suites passed against the frozen production revision
`3699916df590a2fe0ea9b419836ded2d9344e6b3`, system build `c1575e2adfc6fa5d`.
The test source tree is a complete Git export with no overlays. Its **2,196**
recorded system source files match the native manifest. Fixtures were rebuilt
with that system's exact exported SDK inside the Preview 2 environment; source,
SDK and artifact identities were checked again after execution.

| Actual native suite | Rounds | Invocations | Result |
|---|---:|---:|---|
| READY/ACK/exec controller | 3 × 11 cases | 33 | All passed |
| IPC exec, lifecycle, authority and owner quota | 3 × 4 modes | 12 | All passed |
| Absolute IPC deadline | 3 × 1 multi-condition mode | 3 | All passed |

Every invocation exited normally with status zero and restored exactly
**129779 free pages / 2 tasks / 0 completions**. Each suite ran in its own fresh
QEMU guest, serially. These are new integrated observations, not relabeled
results from the earlier source or SDK.

The controller suite includes READY success, cancellation, entry failure,
entry and PREPARE revocation, timeout, early exit, malformed messages, multiple
children, and expired queued ALLOW/CANCEL recovery. It exercises the actual
public wait pump, authenticated native channels and real same-PID exec.

Each IPC lifecycle round proves failed-exec preservation and successful-exec
revocation, then observes genuinely blocked send and receive workers for revoke,
close, exit, fault and cancellation. It requires broken-channel wakeup,
authenticated service restart and stale-token refusal. The authority and quota
modes require subject binding, attenuation, redelegation, one-shot replies,
shared per-owner accounting for pending/accepted/blocked objects, atomic failure,
peer isolation and quota recovery.

Each deadline round checks receive timeout while the peer remains alive, send
timeout without discarding queued payload, expired/zero readiness ordering,
unsupported scope and legacy parameter refusal, actual send/receive readiness
wakeup, and close/no-wrap/final-timeout behavior. The original three-round
requirements and exact resource assertions are unchanged.

`qualification.json` summarizes the observed counts and scope.
`system-binding.json` retains the complete source and artifact manifest with its
frozen source revision. Each suite has separate fixture and guest receipts plus
its actual serial log. The raw receipt digests remain input identities;
`conversion.json` records mechanical export transformations. Only the root
`manifest.json` contains the hashes of exported report leaves.

The native gate covers L1/L2 for this final integrated source. It does not extend
per-PID quotas into process-tree budgets or implement durable cross-descendant
revocation. The runner's explicitly unrun sys81 inheritance stress and separate
terminal/display/Interactium regressions remain outside this focused gate.
New GNU capsule/startup and generation tests have their own exact-byte reports.

Reproduce from a complete export of the stated revision inside Preview 2. Build
`build_launch_control_probe.py`, `build_ipc_exec_probe.py` and
`build_ipc_deadline_probe.py` against `${XOS_NATIVE_SOURCE}/build/system/sdk`.
Then run `tests/launch_control_guest.py --repeat 3`, and
`tests/ipc_exec_guest.py --repeat 3 --serial-only` once with `--suite lifecycle`
and once with `--suite deadline`, supplying that system, the corresponding
fixture directory and a new output directory for each invocation. The source
export must remain byte-identical to the native manifest; do not substitute a
subsequently edited checkout.
