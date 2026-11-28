# fe6b306b P1-B cumulative process budgets and observable Files quarantine

Baseline: `24b57a268681fae38dff5836c8b9cf0837685ae3`, after the four manually
requested issue fixes were merged. Scope is P1-B in `plans/p0_completion.md`.
P1-C/D/E/F remain separate changes; this record does not close their acceptance.
The publication base is `0d0fb72a1ecd077c3240ea33f260a3b3ef500cbb`, which
also includes the independently validated P1-E persistence change (#442).

## Implementation

`process_budget_abi.hpp` adds explicit sys87 modes 4/5 with versioned 64/192-byte
configuration/observation. Existing modes and syscall numbers are unchanged.
The shared native SDK exports the structures, wrappers and manifest metadata.
The six dimensions are processes, logical user/grant pages, threads, IPC
objects, names and pipe objects. Limits supplement existing system bounds.

Kernel-held ancestor masks follow spawn, fork and exec. A child cannot remove
an ancestor or enlarge its limit. Queries expose authorized aggregate and
per-process attribution. Pending fork/VM allocations remain charged across
continuation yields. Pipe and IPC-v1 objects retain the original domain mask
after creator exit; final object destruction returns the credit. Domain slot
reclamation scans both processes and retained objects, and domain IDs never
repeat. An independent review checked fork preparation, VM rollback/publication,
exec staging, reparenting and retained IPC objects without finding a bypass.

Dynamic controllers expose the first quarantine event through a read-only,
versioned snapshot. Unknown OPEN explicitly reports possible remote ownership
without a returned token. Unknown CLOSE retains its known token. The
same-process atomic try-lock rejects competing operations immediately and
inspection preserves its output on rejection. Quarantine cannot be reset by
configure or Files reinitialization.

The isolated Files fault profile drops a reply only after production OPEN/CLOSE
has completed. Its service-side receipt records the actual request ID, operation,
attempt count and committed status. Ordinary images neither contain the hook
nor grant Files the qualification-only console route.

## Actual validation

All target builds and QEMU runs used the published glibc preview-3 Linux SDK
development environment. Native probes link the matching exported native SDK,
without substituting a libc runtime or the host operating system's behavior.
The final test image is build `aa92d5979cf58b82`.

```sh
python3 tests/dynamic_closure_host.py --output build/p1b-closure-host
python3 scripts/build.py --output-dir build/p1b-system-final --quiet-demos-on-launch --files-uncertain-probe
python3 scripts/build_process_budget_probe.py --sdk build/p1b-system-final/sdk --output build/p1b-fixture-final
python3 tests/process_budget_guest.py --system build/p1b-system-final --fixture build/p1b-fixture-final --output build/p1b-guest-final --repeat 3
```

The actual guest passed 27 cases across three repetitions:

| Case | Checked behavior |
| --- | --- |
| family | Nested fork shares the ancestor cap; wider delegation and fourth process reject; pipe/name/IPC limits remain shared; repeated exit/restart restores credits. |
| pages | Fork preflight, heap growth, staged VM rollback/publication and IPC grant backing all respect page credits; a failed staged allocation returns usable credits. |
| IPC | Endpoint, notification, wait-set and grant objects share one cumulative allocation budget and return it on close. |
| alias | A child creates a grant and delegates a real handle to its parent; creator exit retains the object/backing-page charge until the surviving alias closes. |
| exec | Failed exec preserves the budget; successful exec keeps PID/domain identity, advances image generation and releases staging pages. |
| fresh | A separate authenticated process can use Files and install/use its own budget. |
| uncertain OPEN | Real committed OPEN loses its reply; controller records unknown ownership and refuses replay. |
| uncertain CLOSE | Real error-cleanup CLOSE loses its reply; controller records and retains the token, without replay. |
| concurrency | A real native thread holds the controller in a Files wait; another thread receives immediate busy/state results with unchanged observation output. Thread limits and join reclamation also hold. |

Every uncertain case keeps its failed controller alive while a separate process
successfully opens/closes a file and uses its own budget. Service receipts show
exactly one committed side-effect attempt per injected request. Every completed
case returns system free pages, task count and completion count to the identical
baseline. This includes the unknown OPEN whose token was never returned.

The existing closure/verifier host suite passed 46 ordinary and ASan/UBSan
cases. Those Files objects are modeled; this record does not relabel host tests
as guest evidence. LeakSanitizer is disabled by that runner, so no separate
leak-detector result is claimed.

Public results, actual serial transcript and source receipts are under
[`p1b_authority_lifetime`](../reports/p1b_authority_lifetime/report.json), with a
flat, independently verifiable `manifest.json`. Previous frozen reports remain
unchanged. The repository-wide historical manifest checker has its known
pre-existing failures; the new evidence index is checked separately.

## Integration on the merged P1-E baseline

The complete staged change applied cleanly over the actual P1-E merge. A fresh
native SDK and test image, build `c0347772f1d95f02`, then passed all nine guest
cases once more. Every case recovered the same `[129790, 2, 0]` resource
baseline. `integration_report.json` binds this run to its exact system source,
SDK, fixture and ISO digests; `integration_serial.log` contains the actual
transcript with only line-ending and trailing-whitespace normalization. This
additional integration does not replace or mutate the preceding 27-case record.

## Failed attempts and qualifications

The first guest run passed family/page/IPC checks and observed OPEN quarantine,
but its service receipt was absent because production Files correctly has no
console route. The explicit test profile now grants only that observation
route; it does not alter production service authority. A fixture compile also
rejected a misleadingly indented one-line loop under `-Werror`; the fixture was
corrected and rebuilt. An intermediate wrapper used the wrong working directory
for a runner edit; no target source was changed by that failed edit.

No arbitrary physical power-loss, SMP, second architecture or new GNU shared
runtime qualification is claimed. CLOSE deliberately exercises the cleanup of
an invalid manifest through the real loader and Files service. Existing
complete-closure, same-pin and activation-rollback qualifications are retained.
P1-C supplies persistent catalog authority and descendant revocation separately.

Global status is maintained by the integrator at the actual merged milestone;
this worktree does not overwrite parallel modules' state.
