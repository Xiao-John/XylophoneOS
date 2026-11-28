# Independent pipe-reference transfer

This profile extends ordinary child construction with an explicit, atomic grant
of existing private pipe references. It does not allocate a new pipe object or
add a syscall. The registered extension uses `sys_process_stdio` (34), with
arg1 naming an owned building child, arg2 equal to `1ULL << 63`, and arg3 pointing
to a writable v1 `process_pipe_transfer` request. Fixed stdio modes 0–2 keep their
existing behavior.

## Request and authority

The request is exactly 144 bytes: four `u32` fields `version`, `size`, `count`,
`reserved`, followed by 16 `{u32 source, target}` entries. Version is 1 and size
is 144. Count is 1–16; reserved, every input target, and every unused source are
zero. Active sources must be distinct, caller-owned private pipe tokens. A
number copied from another process is not authority.

Only an ordinary building child owned by the caller can receive the batch.
Runnable children, fork-pending children and replacement-pending images reject
the request. A reference already in that child's private table is a state error,
not an extra retain. Each returned target equals its source token; membership
in the receiving PID's private table supplies authority. Direction is copied
from the kernel-held source reference and cannot be changed by the caller.

Malformed fields and inaccessible input/output memory return
`process_error_invalid`. A foreign child or a source absent from the caller's
private table returns `process_error_denied`. Wrong construction state or an
already present target returns `process_error_state`. Insufficient child
reference capacity returns `process_error_resources`. Failure leaves all request
bytes and reference counts unchanged; no partial batch can be used or replayed.

## Atomicity, ownership and limits

The kernel snapshots the complete request, validates every source and child
slot, and prepares all writable output pages, including COW copyout, before the
first retain. It publishes the prepared output mappings, copies each validated
reference and increments the appropriate reader/writer count, then copies out
the completed request. The current kernel syscall critical section is not
preemptible; no fallible allocation remains after the first reference mutation.

The child can hold at most **16 native pipe references**, counting both fixed
stdio routes and private tokens. The system still contains at most **8 pipe
objects**. A batch changes neither the object's `owner_pid` nor its `budget_mask`;
retaining an existing object does not consume a second object credit or return
the original credit early. The original budget domain remains charged after the
creator closes its references or exits, until the last holder releases the
object. Existing abort, child exit and last-reference close perform the cleanup.

Read/write direction, buffer contents and reader/writer closure remain properties
of that same object. Last writer close permits EOF after buffered data drains;
last reader close makes subsequent writes return EPIPE through libc. Aliases of
one open description share one child token and therefore cannot defer these
events through accidental extra native references.

## SDK and GNU composition

`sdk::spawn_options::transfer_independent_pipes` defaults to false. Existing
native callers continue to use fixed stdio routes and reject unrouted independent
pipe descriptors. A caller that explicitly enables the option grants each
unrouted pipe open description once, in one native batch, after descriptor alias
validation and unused-stdio-route retirement. Alias descriptors all receive the
same target token. A later image mapping or callback failure aborts the entire
unstarted child and releases every granted reference. Parent descriptors remain
untouched.

The matching glibc `posix_spawn` bridge enables the option for its validated
inherited descriptor snapshot. `FD_CLOEXEC` entries are excluded, shared status
flags are preserved within each alias group, and the existing **32-FD snapshot**
bound includes ordinary Files descriptors, kernel stdio and aliases. It does not
promise 32 independent pipe objects. The actual bound of 8 objects / 16 endpoints
can coexist with 13 extra aliases and the three console descriptors, totaling 32
FDs.

Same-PID exec retains its existing pipe handles and uses its existing CLOEXEC
cleanup path. Combining explicit transfer with replacement is invalid. Fork
continues to copy native references through its separate kernel transaction; it
does not call this building-child grant. Older kernels reject the new mode and
the loader aborts the candidate; there is no route fallback or partial retry.
Applications, headers, support archives, syscall mode and SDK manifest must come
from the corresponding verified build.

## Qualification

The native guest tests exercise complete-request validation, foreign and stale
authority, a malformed final entry, already granted tokens, an output spanning
one writable and one read-only page, pending fork/exec rejection, the combined
16-reference limit, retained budget charge, abort recovery and real SDK-loader
failure after mapping. A real child checks its native direction and rejects a
known ungranted token. GNU probes cover routed compatibility, independent pipe
aliases, shared flags, CLOEXEC, EOF before child exit, EPIPE, failed/successful
same-PID exec, and the complete 32-FD / 8-object boundary through both shells.
Results are bound separately to the exact system, packaged SDK and programs;
producer manifests are not rewritten as guest observations.
