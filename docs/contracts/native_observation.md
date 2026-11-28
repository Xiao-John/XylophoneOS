# Native read-only observation v1

`sys_observe` (90) is the bounded kernel state source for P1-A. It carries no
model policy, action executor, persistent grant, network address or credentials.
An ordinary program uses `xos::sdk::observe` from the same source-built SDK as
the kernel. The additional user-space observation service and proposal validator
have their own contracts; this syscall does not authenticate a remote client on
their behalf.

## ABI and authority

The authoritative definition is
[`observation_abi.hpp`](../../src/shared/include/xos/observation_abi.hpp).
`sys90(&request, &snapshot, 0)` takes an 8-byte-aligned 48-byte request and an
8-byte-aligned 120-byte writable output. The request must have `version=1`,
`size=48`, zero `reserved`, and a known query kind. Output is copied only on
success; the SDK wrapper clears its output before making the call.

| Query | Authorized target | Fields populated |
| --- | --- | --- |
| `process` (1) | `target=0` or own PID; a directly owned child PID | PID, parent PID, image generation, thread-aware process state, closing flag, allocated thread count and blocked subset, scheduler ticks, observation times |
| `resources` (2) | Same self/direct-child rule | Process fields, user-page count/limit, owned generic IPC pair count/limit, published name count/limit, pipe-reference count/limit |
| `service` (3) | An existing sys84 or sys81 endpoint whose sender or receiver is the calling PID | Peer PID, peer image generation/state, whether it currently publishes at least one name, the supplied endpoint token and observation times |

Supervisor identity does not bypass these rules. Grandchildren and unrelated
processes are not directly readable. A service snapshot does not disclose the
peer's parent, resource usage, scheduler ticks, published name text, other
clients, IPC messages or memory addresses. Unselected result fields are zero.
The endpoint token is the caller's already-held input repeated for correlation;
the snapshot creates no additional rights or transferable authorization.

The resource limits are the existing per-process limits. Generic IPC pairs are
counted once through their canonical endpoint, including pending and accepted
connections. These limits do not describe process-tree budgets, sys81 channel
quotas, IPCv1 objects, global free memory or the complete OS resource inventory.
Thread count includes non-free retained records, including exit results not yet
reaped. Pipe-reference count includes the process's pipe token table and retained
non-console stdio routes; aliases are references, not distinct pipe objects.

## Identity and lifetime

PID and generic endpoint tokens are monotonically allocated and never reused
within one boot. `image_generation` starts at one for every new PID, including a
fork child. A successful same-PID exec increments it; failed exec preserves it.
If it cannot increment without wrapping, exec returns the existing process
resource error before revoking authority, replacing queues or changing images.
A fork has its own PID/generation even though its initial memory came from the
parent. These identities are boot-local; a recording must also bind its boot
or recording session before treating them as stable references.

Nonzero `expected_pid` and `expected_generation` are compared only after the
target has passed authorization. A mismatch is `stale` with no snapshot.
Zero means the caller is requesting the current authorized identity. A stale
endpoint after close/revocation/exec returns `denied`, exactly like a guessed
or foreign endpoint. No tombstone registry reveals which denied tokens used to
exist or who owned them. A still-held endpoint whose peer is missing, building,
dead or closing returns `unavailable`. A service restart requires reacquiring an
authorized endpoint and explicitly checking the resulting new identity.

## Deadlines, bounded work and errors

`deadline_ns` must be a nonzero finite absolute monotonic nanosecond deadline.
Zero and `UINT64_MAX` are invalid. The deadline is checked before scanning,
after scanning, and after preparing the output memory immediately before
copyout. An already-expired deadline fails; cached success never overrides it.
The kernel scans fixed arrays of at most eight processes, 32 thread records,
37 legacy endpoints and eight name records. It allocates no observation session,
queue or kernel object and never waits for a peer or invokes the scheduler.
The caller's output can still require ordinary COW copyout memory.

| Result | Value | Meaning |
| --- | ---: | --- |
| `ok` | 0 | Complete snapshot copied |
| `denied` | -1 | Missing/foreign process authority or missing/revoked/foreign endpoint; no distinction that discloses existence |
| `invalid` | -2 | Unsupported version/size/kind, reserved input, alignment/address or deadline format |
| `stale` | -3 | Authorized identity no longer meets the supplied PID/image-generation precondition |
| `deadline` | -4 | Absolute deadline reached before publication |
| `exhausted` | -5 | Ordinary kernel copyout resource preparation failed |
| `unavailable` | -6 | Held peer has no observable live service state |

`observed_at_ns` and `completed_at_ns` bracket this individual kernel sample.
They do not make separately collected runtime, network or trust snapshots
globally atomic. A page count is an observation, not a reservation: a later
allocation may fail even when the earlier count was below its limit.

## Compatibility, qualification and rollback

No existing syscall number or payload changes. Legacy `sys21` supervisor stats,
`sys50` thread stats and `sys89` CPU accounting retain their contracts. An old
kernel does not provide sys90, so consumers require the explicit v1-capable
matching SDK/kernel profile and must treat refusal as unavailable functionality.
Rolling back to an older kernel also rolls back this optional observation
consumer; a proposal never substitutes for the missing interface.

[`observation_native_host.py`](../../tests/observation_native_host.py) extracts
the production records, implementation and syscall dispatch case into a host
harness. It exercises authorized self/child reads, unrelated denial, post-auth
identity comparisons, scoped counts, held-peer/revoked/restarted service paths,
schema validation, early/late deadlines and output-address rejection under
ASan/UBSan. It substitutes the clock and privileged user-copy boundary. Actual
guest qualification is recorded by the enclosing P1-A delivery; a host pass
alone does not qualify native syscall execution or an installed OS profile.
