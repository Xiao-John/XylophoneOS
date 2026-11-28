# P1-B: cumulative process authority and resource lifetime

## Scope and ABI

`sys_process_authority` (87) adds two explicit modes. Existing modes 0–3 keep
their create-authority meaning and byte layout. Mode 4 takes a 64-byte
`process_budget_config` in argument 3; mode 5 takes a 192-byte
`process_budget_snapshot`. Both use version 1 from
`src/shared/include/xos/process_budget_abi.hpp`. No reserved syscall number or
old reserved field is repurposed. Older kernels reject these modes.

The native SDK exports `set_process_budget(pid, limits)` and
`query_process_budget(pid, output, domain_id)`. The query wrapper preserves
`output` on error. The manifest describes modes, sizes and dimensions; a build
manifest's `not_run` qualification is not a guest test result.

A caller may restrict itself, or an owned unstarted direct child. The target
must not already have a local domain, a pending image replacement, a closing
state, an active VM transaction or existing children. Restrictions on an
existing subtree are deliberately rejected instead of silently missing its
aliases. Existing authority is still required for child construction; installing
a budget does not grant create, file, network or device authority.

## Six cumulative dimensions

| Dimension | Charged lifetime |
| --- | --- |
| `processes` | Every non-free member, including an unstarted child, until actual reclamation. A private exec constructor is excluded from this logical count. |
| `pages` | Mapped user pages in every member address space, pending fork/VM pages, and IPC grant backing pages. A shared mapping consumes a logical mapping credit in each address space; grant backing consumes separate credits until destruction. Exec construction temporarily charges both old and new pages. |
| `threads` | Non-free thread records, including reservations and unreaped join results. A private exec constructor's temporary main thread is excluded. |
| `ipc_objects` | One credit per sys84/86 endpoint pair, sys81 one-way endpoint, or IPC-v1 endpoint/notification/wait-set/grant object. Delegated aliases do not mint a fresh object, and do not release its original charge. |
| `names` | Published generic service names until unpublish, exec revocation or process cleanup. |
| `pipes` | One credit per pipe object, retained until its last reference closes, including inherited aliases after the creator exits. |

Existing per-process and system bounds also apply. These limits are admission
caps, not reservations of otherwise free system resources. They do not promise
CPU time, physical memory exclusivity, device capacity, or a network grant.

Every child inherits all ancestor domain memberships. A new local domain may
only be narrower than each inherited limit vector; there is no clear, reset or
replace operation for an ancestor. Fork copies membership, not available
credits. Exec keeps the original process's membership and domain identity.
Reparenting cannot remove membership.

Domain IDs are monotonic and never recycled. The bounded internal slot is only
reused after no process, pipe or IPC-v1 object refers to it. Objects retain their
creator's domain mask independently of the creator's process record. PID
strings, names, paths, ELF bytes and caller-provided domain IDs grant nothing.

## Transactions and concurrency

The existing single-CPU syscall/continuation gate serializes admission checks
with table publication. Usage is derived from the bounded live kernel tables;
it is not a user-supplied counter or a per-PID allowance copied on fork.

Fork checks its process, main-thread and complete page cost before preparing
the child. The unstarted child immediately reserves the parent's complete page
count. Each copy batch transfers charge from pending pages to mapped pages;
it never makes a temporary gap available to a sibling. Rollback retains the
charge until actual cleanup is complete.

VM commit/protect charges each newly allocated staged page before the next
continuation yield. Publication transfers pending to mapped charge; rollback
releases it with the corresponding page. Heap growth, thread stacks/TLS, child
mapping, IPC grant allocation and IPC grant mapping use the same admission
check. Failed operations retain existing allocations and authority.

This contract describes the current serialized kernel. An SMP implementation
must preserve the check/reserve/publish atomicity before claiming compatibility.

## Observation and errors

Queries are allowed for self and authorized direct children. The default
selects the newest inherited domain; an explicit domain ID must be in that
target's membership. A snapshot includes the stable domain owner PID, target
PID/image generation, aggregate usage and per-target attribution. An unbudgeted
target has domain ID/flags/limits/aggregate zero and still reports attribution.
It does not mean the system has zero free capacity.

Version, size, zero fields and bounds are checked before mutation. Errors use
the existing native families: invalid (`-2`), denied (`-1`), resources (`-5`),
state (`-6`), delegation (`-10`) and busy (`-11`). IPC-v1 and VM operations keep
their existing typed resource errors. A failed query does not publish a partial
snapshot. The existing exclusive process admission guard still blocks sys87.

## Dynamic controller and uncertain Files results

`dynamic::inspect_controller` exposes a 72-byte version-1 read-only snapshot.
It records controller PID, policy sequence, first failed operation sequence,
original failure PID, deadline, operation kind, native error, known token and
retained token count. Its flags distinguish configured, quarantined, uncertain
and unknown-OPEN ownership. Operation sequence is a controller call sequence,
not a fabricated Files protocol request ID.

An unknown OPEN may already have created a remote lease even when no token was
returned. An unknown CLOSE keeps its local token even when the server already
closed it. The first failure remains observable; configure, activation and
new acquisition reject quarantine. Re-initializing a Files client cannot
repair a poisoned session. There is no automatic replay, speculative close,
late-reply reuse or caller-controlled reset. Session/process teardown is the
recovery boundary. An inherited poisoned controller stays poisoned; the
snapshot retains the PID that originally encountered the uncertainty.

Every controller operation and inspection uses the same PID-scoped atomic
try-lock. Concurrent calls in one process return `error::state` immediately;
they do not block behind an operation holding a Files deadline. The application
must serialize controller calls or treat that result as a rejected attempt.
Inspection leaves its output unchanged when busy. The contract does not make
arbitrary concurrent raw `file::client` use safe in a libc-free program.

## Qualification

`tests/process_budget_guest.py` drives ordinary exported-SDK clients against the
actual kernel and Files service. Its explicit `--files-uncertain-probe` image
drops a selected OPEN/CLOSE reply after the production operation has completed.
The isolated image gives Files console output for operation receipts; ordinary
images have neither this hook nor that console route. No guest fault-control
syscall or production debug operation is added.

The failure manifest used by the CLOSE case deliberately fails validation:
the test exercises the real error-cleanup CLOSE, whose reply is then lost.
It does not claim to qualify a new GNU runtime generation. Existing complete
closure and same-pin qualification remains separate. Host closure tests use
modeled Files objects and are labeled accordingly; real guest evidence supplies
the uncertainty and resource-lifetime acceptance.
