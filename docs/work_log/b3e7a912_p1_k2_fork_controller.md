# P1-K2 dynamic fork controller migration

## Final result

The final frozen system `15362d9ea4b71917` passed all **13 actual QEMU target
cases** in `build/k2_guest_v6`: ten fork/controller cases through xsh and
dash, two independent dynamic-pipe executions, and explicit controller plus
descendant cancellation. Every case restores **129789 free pages, two tasks
and zero completions**. The terminal-actor protocol remains a separate
implementation and qualification.

The [published-form local evidence](../reports/p1_k2_fork_controller_20261128/README.md)
retains complete source/artifact and SDK bindings, sanitized derived reports,
lossless serial transcripts, all five failed development runs with their
original status, host adapter checks and measured exec durations. It is
prepared for the coordinating agent's independent PR review; this local
record does not claim that publication or merge has already happened.

## Scope and implementation

This work starts from the P1-K1 elapsed-wait implementation and P1-K5
independent-pipe implementation on the registered P1-K2 fork offer ABI. It
enables `fork` / `_Fork` in the public fixed-startup shared GNU profile. The
private shared profile keeps its unsupported stub. Terminal actor composition
is a separate change and is not qualified by this record.

The child receives a fresh direct-parent-owned READY/ACK pair and an exact
128-byte `xos_fork_control_offer`. The parent retains its own upstream pair.
The adapter authenticates native channel metadata, resets copied runtime
state. The parent returns after authenticating READY and enqueueing its ACK;
the child returns after receiving and validating that ACK.
One absolute five-second deadline bounds the whole admission sequence. Native
thread-profile admission and create authority remain in force.

The Files clone is completed under its existing lock, which is then released
before controller admission calls back into Files. A prepared child remains
non-runnable. The parent creates the pair and retains the offer, commits the
native child, then sends the offer exactly once. A send or READY failure after
commit cancels and reaps the child. Failure before commit aborts the building
child. Controller PREPARE failures are reported at the start stage so the
public errno mapping preserves denial rather than treating it as a bad ELF.

Modified production areas are the libc fork adapters and Files fork path,
`src/user/loader/dynamic/spawn.cpp`, the standalone fork offer header, the
shared-runtime composition manifest, and the explicit `dynamic-run
--without-create` fixture launcher option. The option clears authority on the
owned building child; it does not attempt an unsupported self-clear.

The focused target fixtures cover nested direct-parent controllers, failed
and successful same-PID exec, copied then reinitialized TLS, FD aliases and
CLOEXEC, inherited Files cursor behavior, independent pipes, ordinary
controller exit, explicit descendant cancellation, and denied create
authority. The C-only closure has no approved GCC unwinder. Its thread-profile
fixture checks the actual bounded rejection path; it does not claim a running
GNU worker or worker TLS cleanup.

## Implementation checkpoint verification

This is a local implementation checkpoint, not a completed target
qualification. Host `tests/dynamic_fork_host.py` passed ordinary and
ASan/UBSan runs in `build/k2_fork_host_v4`: 10 groups, 12 malformed-offer
variants and 7 begin-rejection variants. The fixture includes the production
adapter and explicitly models native rejection of sends to building children.
LeakSanitizer is disabled for this host environment. `git diff --check` and
Python compilation of the new runners also passed.

The first complete real guest attempt, `build/k2_guest_dev1`, bound system
`cb18a8d4dab4db6b`, C SDK v1, public shared runtime v1, both C generations and
the approved launcher before starting QEMU. The first fork case failed:
native IPC rejected delivery to a building child, before commit, and the
application returned an error. No target case is counted as passed. The full
serial/QEMU logs, failed report and input hashes are retained. This failure
identified the post-commit send ordering now checked by the host fixture.

The producer builds used the SDK's GCC 16.2.0 and QEMU 11.1.3. The full locked
glibc 2.44 and GCC 16.2.0 archives were verified before extraction. The shared
builder's source-space optimization was exercised successfully: GCC test-suite
members were not materialized, while signature and hash verification still
covered the complete original archive. The PIC startup objects compiled.

The corrected source is now frozen for new outputs `build/k2_sdk_v2`,
`build/k2_system_v4` and then a matching `build/k2_runtime_v2`. Representative
commands, inside the selected authenticated SDK environment, are:

```sh
python3 tests/dynamic_fork_host.py --output build/k2_fork_host_v4
python3 scripts/build_glibc_sdk.py --archive build/inputs/glibc-2.44.tar.xz --output build/k2_sdk_v2 --jobs 2
python3 scripts/build.py --output-dir build/k2_system_v4
```

The final shared-runtime build must supply both independently inspected C SDK
anchors. The program and launcher builds must additionally bind the complete
native SDK and approved generation roots. Old v1 artifacts are preserved as
failed-attempt evidence and are not relabeled as the new source's output.

Only verified, reproducible intermediate source/configuration/object trees
from this branch's old producer outputs have been removed for disk space.
All declared artifacts, manifests, source-verification receipts, logs and
the failed guest report remain, with local cleanup receipts.

## Checkpoint follow-up

The checkpoint required a matching full guest run, preserved failure
records and sanitized source-bound evidence. These local tasks are completed
by the final qualification below. Publication and the global state, plan and
ABI fact updates belong to the coordinating root agent. The independent
terminal composition retains its separate implementation, evidence and PR.

### Final target attempt v2 — preserved runner failure

The frozen production checkpoint `98311717` passed the first eight actual
QEMU cases: direct fork/exec, nested controllers, attenuated authority and the
thread-profile rejection, each through xsh and dash.  In owner-exit-xsh both
application PASS records and the orphan resource reclamation appeared, but
the shell prompt preceded the asynchronous orphan record on the same line.
The runner required the record at column zero and therefore correctly kept
this attempt failed.  Its raw report and serial output are retained in
`build/k2_guest_v2`.  The follow-up accepts one exact `xsh> ` prefix only for
owner-exit result lines and still requires the entire result line to match;
no production implementation or expected result was relaxed.  A fresh native
system, matching stages and launcher will be built before the full rerun.

### Target attempt v3 — independent dynamic-pipe lifecycle watchdog

System `2bbfede5fb783567` passed all ten direct/nested/authority/thread-profile/
controller-exit cases through xsh and dash. The shared dynamic pipe probe also
passed aliases, flags, CLOEXEC and EOF-before-child-exit. Its next case reached
actual `exec_replaced` with the same PID, then its parent exhausted a single
five-second fixture watchdog while waiting for pipe output. That watchdog
incorrectly covered a failed exec, a successful exec and subsequent pipe I/O,
each of which has its own bounded phase. The run remains failed in
`build/k2_guest_v3`; it is not promoted to pipe qualification.

That follow-up gave only this aggregate exec lifecycle a fifteen-second
watchdog and carried monotonic timestamps across exec. It incorrectly
assumed the five-second fork admission limit also bounded exec, adding a
strict five-second full-call assertion. The v5 result and correction below
supersede that assumption. The C SDK and shared-runtime production inputs
were unchanged.

### Target attempt v4 — controller exit during adoption

System `ca9961c930da2efd` again passed the first eight cases, then the
owner-exit fixture let its controller return immediately after enqueueing the
child's READY_ACK. The controller exited before the child consumed that ACK.
The child was reclaimed without its post-fork result, consistent with the
documented status-127 path for interrupted adoption. This run remains failed
in `build/k2_guest_v4`; its original report and serial evidence are retained.
It did not reach the revised dynamic-pipe timing checks.

The post-adoption owner-death case now requires a byte from the child after
its `fork` returns. The parent polls that inherited nonblocking pipe under a
five-second monotonic deadline, pumps the public wait path, and fails if the
child terminates first. Only after consuming the byte does the parent print
its adoption marker and exit. The runner requires this additional complete
marker. This selects the intended completed-adoption failure boundary rather
than changing the production READY/ACK protocol. The contract now states
explicitly that enqueued ACK does not guarantee its receipt. A fresh native
system and all thirteen original cases will be rerun.

### Target attempt v5 — correct the exec budget assumption

System `32bebd006926c926` passed all ten fork/controller cases, including both
synchronized post-adoption owner-exit paths. The first independent-pipe
group passed. The next child reached actual same-PID `exec_replaced` and its
new main, then failed the fixture's newly added five-second duration
assertion. That predicate was checked before printing the values, so this
failed run does not provide a numeric exec-duration measurement.

The fixture had incorrectly reused fork's five-second limit. The existing
`src/ports/glibc/spawn_support.cpp` exec adapter, the
`startup_deadline_limit_ns` constant in `xos/dynamic_abi.hpp`, and both actual
version-1 generation headers carry a thirty-second startup budget. The
closure reader bounds its selected deadline by that budget. None of these
production values changed in this work. The run remains failed in
`build/k2_guest_v5`; this is a correction to the test's assumption, not an
increase in the production deadline.

The runner now reads and requires the actual thirty-second field in each
bound generation. The fixture prints both full-call durations before their
assertions, checks the observed durations against thirty seconds, and allows
sixty-five seconds for the two-call-plus-I/O aggregate. Fork admission and
the post-adoption confirmation retain their separate five-second deadlines.
These measurements describe the calls observed in this fixture, not a new
universal exec latency guarantee. A new native system, matching stages and
approved launcher will precede another complete thirteen-case run.

### Final target attempt v6 — all thirteen cases passed

The frozen code and fixtures at `5bd941b2` produced system
`15362d9ea4b71917`, its full packaged native SDK, both C generations and the
approved launcher. The complete run passed with GCC 16.2.0 and QEMU 11.1.3.
The native SDK manifest is
`15ad4189e12fb3ec1662adf1ece0c5a03555a4fccffc1b202c188aeb4522e213`
and its full-tree anchor is
`f2e85b8b3343a02cf33be6979fce6c60c10778a8b88934c55ebdae1d9453e226`.
The independently verified C SDK retains manifest
`a4599d0c55130809bd53519033b3d8b8dfdefa500edc593ed79db1d1cff78d31`
and tree
`03a53d3ad3a1d82a7f38653d4b45c9a80ae5751a747cb4ed92c3e0b6aa20d3a1`.
Its matching public shared-runtime manifest is
`9fdddaa5ef9998a20081b5eedfea9303a2b6c884aede6e6dc6e0938334089064`.

The runner reads the actual thirty-second startup-budget field in both
approved version-1 generations. The two independent pipe executions observed
failed exec at 20,000,000 ns each, and successful same-PID exec through the
new main at 5,890,000,000 ns and 5,550,000,000 ns. These measured values also
explain why the previous five-second fixture assertion was invalid. The
production budget was not changed. All four pipe behavior groups ran in
each execution: shared aliases/flags/CLOEXEC/direction/EOF before child exit,
failed and successful exec preservation, last-reader EPIPE, and the bounded
eight-object/sixteen-reference/thirty-two-FD capacity.

Both normal-controller-exit cases first proved that the child had returned
from fork, then checked dead-controller rejection, PID/FD preservation and
reclamation. The cancellation case killed the controller and its descendant
and returned to the same exact resource baseline. No C++ closure, successful
GNU worker in this C-only closure, terminal actor, SMP or physical hardware
claim is made by these runs.

The actual final runner invocation, inside the selected authenticated SDK,
was:

```sh
python3 tests/dynamic_fork_guest.py --system build/k2_system_v8 --system-source . --runtime-build build/k2_runtime_v2 --runtime-source . --launcher-build build/k2_launcher_v6 --launcher-source . --dash-receipt build/k2_dash_v2.json --dash-source . --dash-sdk build/k2_sdk_v2 --stage build/k2_fork_stage_v6 --stage build/k2_pipe_stage_v6 --output build/k2_guest_v6
```

The evidence exporter rechecks every final guest-bound input, the full system
source/artifact inventory, complete native and C SDK snapshots, all nine
shared-runtime artifacts and the production host-fixture sources. Historical
failed runs are verified through their original evidence manifests; they are
not claimed to have used the final source. The flat public directory manifest
is the only hash inventory for exported leaves. Original input/report hashes
remain explicitly identified as external source bindings.

### Final evidence checks

The exact staged report and work log passed the public-path scanner with
20 files selected and 20 scanned, no findings. The flat evidence manifest
verified all 18 leaves. The repository report-manifest check lists this new
directory as compliant; its overall status remains failed because 17 existing
manifest violations in unrelated inherited report directories remain. Those
frozen directories were not changed or presented as passing. The final
documentation change does not alter the frozen producer or guest inputs.
