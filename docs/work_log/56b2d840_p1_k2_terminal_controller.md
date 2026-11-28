# P1-K2 independent terminal actor and dynamic exec

## Scope

This is the separate terminal composition change requested alongside the
fork-to-exec controller protocol. It is based on local fork implementation
checkpoint `98311717` and the already registered sys81 action-7 extension.
The coordinating agent owns the global ABI/state/plan updates and separate
PR delivery. The final single-run target qualification passed seventeen
checks at source `6b513fff`; its complete result is recorded below. Earlier
pending and failed entries retain the state of their original checkpoints.

The native kernel now implements explicit `create_extended` with the existing
32-byte request and six-channel owner bound. Legacy create keeps four and
fork-pair derivation keeps eight. Controlled PIDs, direction, ownership,
reserved/third-argument validation, the global endpoint pool and cumulative
IPC budgets retain their existing checks. The SDK exposes the explicit
helper and an opt-in final argument to launch registration. Only terminal
dynamic startup selects it.

The native loader authenticates the terminal pair and optional independent
READY/ACK pair before constructing an exec replacement. It accepts two or
four distinct native endpoints with exact roles; it does not increase the
existing sys60 preservation bound. A fresh terminal v3 FD startup initializes
the actor sequence to one. Successful exec continues the existing sequence.
The terminal owner can differ from the direct launch controller after fork.

The implementation changes the kernel's sys81 creation branch, shared/SDK
channel declarations, launch registration, dynamic spawn selection and
native loader preflight. SDK manifests describe the explicit mode. The
separate contract is `docs/contracts/dynamic_terminal_controller.md`;
channel and loader SDK documentation link that contract.

## Test construction

The dedicated supervisor uses a real COM1 terminal service. Its public GNU C
application starts with terminal descriptors and two independently transferred
pipe endpoints. The initial target plan required two rounds of direct exec,
fork-to-exec, denied creation authority, direct controller exit, explicit
controller cancellation and terminal actor death. They check constructor
terminal access, terminal sequence continuity, PID/TLS/FD rules, aliases and
CLOEXEC, copied token rejection, actual input/output and exact native resource
return. Separate native cases test legacy/extended channel limits and a
cumulative budget that permits five endpoints but denies the sixth. A
failed startup after terminal attach must roll back a partial launch pair,
child, FD references and actor application worker.

Approved generation roots are compiled into the supervisor, never approved
from adjacent run-time files. `scripts/build_dynamic_terminal_supervisor.py`
binds the full producer system, approved launcher, both SDK snapshots and
source inputs. An explicit `--dynamic-terminal-supervisor` system build embeds
only that verified ELF. It compares every used native header, CRT, linker
script and archive byte for byte with the producer SDK. The two complete
system/SDK manifests and build IDs remain distinct and independently bound.

Native compilation now maps the exact build directory to `./build` after its
existing root prefix map. This removes output-directory variation from
archive debug paths. Both producer and test systems are built anew from that
recipe; existing anchors and artifacts are not rewritten or relabeled.

## Initial host checks and build preparation

The production preservation validator passed ordinary and ASan/UBSan runs in
`build/terminal_host_v3`: 9 groups with 9 metadata-rejection variants. The
launch-control fixture passed 16 cases in each mode, including explicit
six-channel selection and cleanup when the second endpoint fails, in
`build/terminal_launch_host_v1`. The production fork adapter also passed its
ordinary and sanitized regression in `build/terminal_fork_host_v1`. Host
LeakSanitizer is disabled in this environment. These are modeled-boundary
checks, not target runs.

An initial terminal host fixture did not compile because its mock counter
collided with the SDK's `length` function and it lacked the standard
initializer-list header. The failed log remains in `build/terminal_host_v1`;
the counter/header correction and later production-source-bound runs passed.
The freestanding supervisor and C application passed host syntax checks with
warnings as errors. Python compilation and `git diff --check` passed.

The first matching static C SDK and ordinary producer system are being built
as `build/terminal_sdk_v1` and `build/terminal_base_v1`. The shared runtime,
single approved C generation, independently compiled supervisor, explicit
test system and real guest qualification must follow, each with complete
source and artifact bindings. Representative commands are:

```sh
python3 tests/dynamic_terminal_host.py --output build/terminal_host_v3
python3 tests/launch_control_host.py --output build/terminal_launch_host_v1
python3 tests/dynamic_fork_host.py --output build/terminal_fork_host_v1
python3 scripts/build_glibc_sdk.py --archive build/inputs/glibc-2.44.tar.xz --output build/terminal_sdk_v1 --jobs 2
python3 scripts/build.py --output-dir build/terminal_base_v1
```

The shared producer must receive both independent C SDK anchors. The program
and approved launcher must use the matching producer native SDK; the test
system must preserve its separately verified identity. Actual target
failures and final results will be appended here and exported in a flat
integrity-manifest report. This record does not claim a normal shell terminal
launcher, arbitrary channel capacity, a running GNU worker in the C-only
closure, or complete target acceptance before that run occurs.

## Actual terminal owner death fixture checkpoint

The original `owner-exit`/`owner-kill` case labels refer to the direct dynamic
controller. A separate test now terminates the real TTY channel owner S.
There are five distinct identities: S, the real COM1 actor T, the surviving
dynamic controller A, its GNU child B and an independent native observer W.
A first receives B's internal read-entry notification, then uses authorized
sys90 observation of its direct child to establish that B is waiting with
one thread and one blocked thread. Only then does S receive permission to
exit. S retains the observer pipe writer and all terminal channels until its
actual normal process exit. It does not close the terminal sessions manually.

W has no terminal descriptors or device permission. Its owner-pipe EOF and
native self-observation with parent PID zero independently establish S's
exit. B must receive EPIPE within the original ten-second bound, reject both
old terminal tokens, retain its separate A-owned READY/ACK pair, reject exec
with EIO while preserving PID, authority, Files cursor and independent pipe,
and exit normally. A waits B and checks the shared Files cursor before its
own exit. W writes and syncs a fixed 1,184-byte report containing this run's
32-byte random nonce, S's page/stack/object account, three event records and
the final stable observer-plus-Files state. The host stops QEMU before cold
reading the disk and compares every required field and nonce.

An independent cold boot with the same observer ELF, system and payloads
measures the calibration state after S exits without creating T/A/B. The
actual owner-death run must finish with exactly the same free pages, task and
completion counts, observer page/stack count and owned objects. This avoids
estimating S's page-table cost or reusing a baseline that still contains S.
Both measured net page returns and S's separate user/stack account remain in
the report. This covers normal owner exit; owner kill and COM1 recovery after
S exits are not claimed.

The new C/observer sources and Python runner passed syntax checks with
warnings as errors. These checks are not a target result. The native producer
system must be rebuilt as `build/terminal_base_v2` because the new test files
are part of its source inventory. The completed C SDK v1 has unchanged
production inputs and was verified in full before and after removing only
GNU source/configure intermediates. Its anchors are manifest
`cc99728fc07e1d386e4256e87a6f5d4300e6cdeb1bb6173d4e5be964f41b01d5`
and tree
`6595e0edf1f16a3fdd7af0ea873b5e71559baf92b88f2cfb2050d58e6d6114ed`.
The shared runtime is building from an exact archive of production checkpoint
`5cc572eb` in an isolated temporary workspace; all runtime recipe, port and
native inputs are rechecked against the qualification checkout. No build
receipt is rewritten to accept a different source or SDK identity.

Pre-target review found that the native observer's ELF must explicitly opt in
to startup-v3 FD restoration. The ordinary native CRT intentionally carries
no such marker. The fixture now declares its `.xos.exec` receiver metadata
and validates the entire two-descriptor snapshot, including bounds, roles,
objects and exact granted tokens, before using the observer pipes. This is a
test receiver fix; it does not change a production ABI or library. The
in-progress producer v2 is development output and will not be relabeled as
final; the corrected frozen fixture requires a fresh v3 producer. Native
syntax validation still passes with all warnings treated as errors.

The durable observer path additionally writes a separate nonce witness only
after the report's real Files sync returns success. Cold host verification
requires that matching witness as well as the complete report; a previous
boot's witness cannot validate a fresh nonce. This ensures an ignored sync
error cannot become a passing receipt. This final fixture review supersedes
the in-progress v3 development producer; the frozen v4 producer will carry
both receiver opt-in and sync-witness checks.

### First target-link attempt: image-size gate retained

The first explicit supervisor linked successfully but was rejected by the
existing 128-KiB native image gate: with debug information removed it was
139,064 bytes. Its failed receipt remains in `build/terminal_supervisor_v1`.
ELF inspection showed the excess was nonallocated symbol/string-table data.
Removing those tables produces a 119,688-byte standalone image. The producer
now compares every program header, loaded byte, allocated section and BSS
layout before and after `--strip-all`, including the exact startup-v3 opt-in
metadata. The comparison passes for the actual first-link artifact. Only
nonruntime symbols are removed; the native image limit is unchanged.

This producer-recipe change requires the fresh final native producer v5,
matching generation/launcher and supervisor v2. The C SDK and shared GNU
runtime retain their independently verified production inputs. No prior
producer receipt is rewritten or treated as target qualification.

### Direct-controller exit synchronization

The parallel fork qualification exposed a real ordering boundary: its
controller could exit after enqueueing READY_ACK but before the child
consumed it. The committed child then follows the existing failed-adoption
exit path, rather than entering the intended post-adoption owner-death test.
The terminal fixture's direct-controller exit case had the same sequence.
It now requires a byte sent by the child after `fork` returns, using a
separate inherited nonblocking pipe and a five-second monotonic deadline,
before informing the supervisor and returning from the parent. Public
nonblocking wait pumps controller work and detects premature child exit.
The true bootstrap TTY-owner death case already verifies child read entry and
its native blocked state, so its boundary is unchanged.

This is a test-only synchronization change. The fresh native producer v6,
generation, launcher and explicit supervisor bind it; the verified C SDK and
shared GNU production inputs remain unchanged. No terminal guest has yet
been run or counted as passing.

### First actual guest: preserve the existing foreground lifetime

System `458bceff6ce9e1f6` passed the native channel checks and the first direct,
fork and attenuated-authority exec cases. Each restored 129371 free pages,
three tasks and one completion. The direct-controller exit case then sent a
failure packet. The supervisor printed its label but not the numeric packet
value, so this failed run does not identify the exact child assertion.
`build/terminal_guest_v1` retains the original failed report and full serial
transcript; the remaining cases and both cold owner-death phases were not run.

Source review and an independent review of the pre-existing contract found
that the new test had assumed an unsupported orphan terminal lifetime.
`terminal_control.md` already specifies that closing the root application
ends the foreground group. `terminal.cpp` implements that rule by closing all
derived sessions while the actor and supervisor remain alive. The new
dynamic-composition contract and fixture now retain that existing policy:
after completed fork adoption and parent exit, the child waits for native
endpoint revocation, rejects its old tokens, observes terminal failure and
failed replacement while preserving PID, authority, Files and pipe I/O. The
supervisor then continues through the same actor. The separate actual TTY
owner-exit experiment remains unchanged. Failure diagnostics now include the
received packet kind and value through the real actor control stream.

The review also identified a transport error-mapping gap. Native invalidation
returns `-1` both to an already pending channel wait and to operations on a
now-invalid endpoint. The old terminal client passed that value to GNU as
`EACCES`, even for a previously established session. The client now converts
only the exchange's native transport-invalid result to the already defined
broken-stream `-7`/`EPIPE`, after its existing endpoint cleanup. Initial
authentication refusal and complete matching denied service replies retain
their original errors. Timeouts, interruption and malformed replies remain
separate. The cleanup does not retry or imply that the original request was
unexecuted; later use of the cleared session remains `EIO`.

This production change requires a fresh C SDK, public shared GNU runtime,
native systems, stages and approved supervisor before target qualification.
All completed v1 producer artifacts remain bound to their original source.
The focused existing GNU terminal host suite is being extended with the
wait/send/receive close races, authenticated denied replies and failed fork
registration, in ordinary and ASan/UBSan execution. Those modeled checks do
not replace the new actual terminal run.

### Second actual guest: retain the budget-resource failure

The refreshed C SDK and shared runtime were built from the terminal transport
fix and verified against every declared source and artifact. The C SDK
manifest is `7ecb486bb4394ebfbaa501d1d9a2e89325b9e9703213f7d75593a6c154fdf322`,
its full tree is `0242c746a71ef2de775d3ec1e4c1d2b32b7dbe67401688622832bd48864a3dd9`,
and the nine-artifact public runtime manifest is
`7b917bc18fb0403d56b9a0a9fb6c479dd101d0e1ae154824eaa638823d3282d4`.
The existing host terminal suite passed all 32 cases in both ordinary and
ASan/UBSan execution, including all three added transport close timings,
authenticated denied replies and failed fork-registration cleanup.

System `83ace96c432855b7` passed the native channel quota/ownership check and
all twelve ordinary application cases: two rounds of direct, fork, attenuated
authority, direct-controller exit, explicit cancellation and actor death.
Each application case returned to exactly 129371 free pages, three tasks and
one completion. The following budget phase failed the unchanged five-second
exact-resource predicate. Its old generic label did not distinguish direct
budgeted channel-create/abort cleanup from the partially allocated dynamic
launch pair cleanup. The run remains failed in `build/terminal_guest_v2`;
neither real-owner cold-boot phase ran.

The fixture now labels each cleanup boundary and prints all four expected and
observed native resource fields before failure. It also emits a separate
marker after the direct cumulative-budget test. The resource equality and
five-second native deadline are unchanged. A fresh native producer, stages,
controller and explicit supervisor will bind this diagnostic change. The C
SDK and shared runtime may be reused only after their full input and artifact
inventories are checked again; no old receipt is rebound to the new fixture.

### Diagnostic v3 and its independent repeat: retain the unresolved stop

Frozen system `2195b86e31435bdd` first passed native admission and direct exec,
then stopped after `DYNAMIC_TERMINAL_FAILED_EXEC_PRESERVED fork` without its
new-image input marker. The ninety-second host deadline expired. An independent
repeat of the identical system and generation passed the entire first round
and direct exec in the second round, then stopped at the same fork boundary.
Neither run reached the budget diagnostics. Both original failed reports and
serial transcripts remain in `build/terminal_guest_v3` and
`build/terminal_guest_v3_repeat`. Their generation and the preceding v2
generation are byte-identical, as are all 190 native compilation inputs used
by their supervisors. The available output does not prove a specific reason
for these two stops.

Review found another fixture budget mismatch: the supervisor's ten-second
packet wait also covered fork admission, failed and successful exec and
post-exec Files/pipe/TTY operations. The existing generation allows thirty
seconds for startup; the invalid-argument exec in this fixture is a local
preflight rejection. The positive completion wait now has an explicit
sixty-five-second aggregate allowance for these phases. Death-case waits,
five-second fork admission, thirty-second production startup and five-second
exact resource recovery are unchanged. This adjustment is not claimed as a
proven explanation of the uninstrumented v3 stops.

The GNU fixture now prints a validated new-main marker and both observed
monotonic exec durations before its sample-duration assertions. The supervisor
records its actual packet-wait duration. The host reads the actual generation
header's thirty-second field and requires these complete timing records. This
will show whether execution reached the validated new-main marker and whether
a successful composite operation exceeds the former ten-second outer wait.
The presence of that marker proves the preceding constructor, TLS, identity
and descriptor checks completed. Its absence does not by itself identify a
pre-main failure: the constructor's mode query or the marker's TTY write may
also be waiting.
These observations do not establish a universal full-call exec latency bound.
A fresh native producer, program, controller, supervisor and test system will
bind these diagnostics; the unchanged production SDK/runtime inputs are
reverified before reuse.

### Diagnostic v4: repair two observation-order errors

Frozen system `af70480adab9e5c1` passed the native channel admission check,
then its host runner failed at the first direct case with an uninitialized
`output` variable. The newly added timing parser ran before the current case's
serial slice existed. The run remains failed in `build/terminal_guest_v4`;
it did not qualify a positive application case or reach either budget cleanup
or the real-owner cold boots.

The host now waits for input readiness and supplies input at the original
position, then parses both complete timing records from this case's bounded
serial slice after its success marker arrives. An independent review also
found that the supervisor attempted its completion timing control write
before the existing detach had joined the actor's foreground worker. The
existing actor may deny that write while the worker is still present. The
fixture now retains the measured duration and prints it only after detach and
exact resource recovery, before its case success marker.

The same actor policy can hide a fatal supervisor diagnostic emitted while a
foreground worker is attached. Consequently, the missing failure text in v3
does not prove an infinite controller-poll wait. This revision does not add a
fatal detach through the existing control helper because that helper's
transport wait is unbounded. All existing deadlines, resource predicates,
production code and owner-death roles remain unchanged. A fresh native base,
program, controller, supervisor and test system bind these fixture corrections;
the full C SDK/runtime inventories are checked again before reuse.

### Diagnostic v5: establish the actor before the rollback baseline

Frozen system `943bcc797b95a8e4` passed native channel admission and both
complete rounds of six application cases. Each case restored exactly 129369
free pages, three tasks and one completion. All six positive cases emitted
complete new-main and completion timing records within their existing sample
budgets. This does not retrospectively identify the two v3 stops.

The cleanup diagnostic then identified the failing boundary as
`partial-launch-pair-cleanup`: expected `129505,3,1,0`, observed
`129369,3,1,0`. Only the free-page field differed, by 136 pages. The observed
tuple exactly matched this system's already measured stable actor state.
The test had called `terminal::start` and immediately captured its baseline,
before the new actor created its permanent receive and control workers.
Attaching the attempted application completed that initialization. Thus the
post-rollback comparison included persistent actor resources absent from its
own baseline. The direct cumulative-budget create/close/abort phase completed
before this later failure.

The raw supervisor print between the two phases was not visible through the
actor after prior terminal ownership changes. Consequently the host reported
its missing budget marker even though the complete serial transcript contains
the subsequent partial-launch failure and precise resource tuple. The original
run, full transcript and receipts remain failed in `build/terminal_guest_v5`;
the real-owner cold boots still did not run.

The budget tail now starts its replacement actor and sends the existing
budget-success marker through an authenticated control roundtrip before
`run_case` snapshots resources. That response both makes the marker visible
and proves the actor's permanent workers are initialized. The exact four-field
resource comparison, five-second recovery deadline, partial READY/ACK denial
and final IPC usage of two are unchanged. No sleep, resource tolerance or
production behavior is added. Another freshly bound native combination will
run the entire suite, including the two cold owner-exit experiments.

### Diagnostic v6: preserve observer privilege boundaries

Frozen system `a31369caf2f03b78` passed all fifteen ordinary and native checks.
The authenticated actor initialization fixed the partial-launch baseline:
both exact resource restoration and final IPC usage of two passed without a
changed timeout or tolerance. The cold calibration then wrote a nonce-matching
1,184-byte version-1 failure report at its final-resource loop, line 101,
with the native timeout result. Its success witness was correctly absent.
The run remains failed in `build/terminal_guest_v6`; the actual owner-death
cold boot did not run.

Three independent source reviews identified a concrete fixture error. The
ordinary spawned observer lacks the bootstrap-supervisor bit required by
`sys_process_stats`. The SDK convenience wrapper discarded that operation's
denied result and returned a zero-initialized structure. The observer therefore
waited on a task count of zero. This result does not show a process-completion
leak. The observed owner-pipe EOF, completed setup transfer and failed report
remain useful diagnostic evidence, but do not qualify final cleanup.

The observer now checks raw syscall results. It explicitly requires that the
privileged statistics query remain denied without modifying its sentinel
buffer. Existing unprivileged thread statistics supply actual global process
and free-page counts together with its own thread/page accounting. Existing
native self-observation supplies parent identity and channel/pipe references.
The private durable report is version 2, 1,224 bytes; it names its own thread
results explicitly and never presents them as global process completions.

The original exact global completion requirement is retained through an
independent host observation. A read-only QMP sampler binds the same kernel
ELF and source/symbol layout, pauses the VM for three small physical-memory
reads, and resumes it. Two late samples must match exactly with two processes,
zero global completion records and free pages equal to the native observer's
report. Calibration and actual owner-exit samples must also match exactly.
The sampler preserves raw bytes and commands, does not modify memory and
adds no guest supervisor, device or process-creation permission. Another
freshly bound native combination will execute this full revised evidence path.

The sampler is independently committed as `e9fe39f2`. Its ordinary and pinned
SDK host suites each passed 31 checks against the actual v6 kernel ELF and
manifest. These include exact symbol/BSS/physical layout rejection, distinct
completion objects, failures during stop/read/resume, retained byte decoding,
sample ordering and native-counter disagreement. QMP transport is simulated
in those host tests; the new cold guest phases remain responsible for actual
physical-memory observations. The reports are in
`build/terminal_resource_snapshot_host_v1` and
`build/terminal_resource_snapshot_host_sdk_v1`; the SDK report's original hash
is `8157a2dbc163949591907b6d387a2d66209d7710f0b55053fc92ffe03fd2d87a`.

### Diagnostic v7: independent cold media and actual resource samples

Frozen source `1e4f397a`, test system `9a782419b7e75b9e`, passed all fifteen
ordinary/native checks. QEMU then failed before the calibration guest could
boot because the environment rejected creation of its Unix QMP socket with
`Operation not permitted`. The original failed run retains its nonce, empty
calibration serial log and QEMU error; it contains no actual resource samples.

A complete fresh run of those same frozen artifacts explicitly selected the
existing FIFO QMP transport inside the SDK command environment. All fifteen
ordinary/native checks passed again. The independent calibration also passed:
its durable 1,224-byte report and sync witness matched the fresh nonce, and
both actual late QMP samples showed exactly 129553 free pages, two processes
and zero global completion records. Those values matched the observer's
checked native statistics; its self-accounting and denied privileged query
also satisfied the unchanged predicates.

The actual owner-exit phase did not boot. Its attempt to import a new nonce
into the calibration disk failed with FatFs result 8, `FR_EXIST`. The host
import command deliberately uses create-new semantics, so retaining the old
nonce made the second import invalid. The run in `build/terminal_guest_v7_pipe`
remains failed with sixteen passed checks, including the complete calibration
and its raw QMP bytes. That partial success is not a full qualification.

The runner now closes the previous VM, retains its final disk digest, and
formats/populates a new private test disk for each cold phase from the same
verified payload. Each phase records that payload, its pre-nonce and input
disk hashes, and its final disk hash alongside the independent random nonce,
report, witness and resource samples. No old report or witness can carry into
the second experiment. The shared disk utility's create-new rule is unchanged.
All deadlines, guest permissions, native and global resource predicates remain
unchanged. A fresh source-bound native combination will rerun all seventeen
checks; no earlier partial run is combined with its results.

## Final actual qualification

Frozen source `6b513fff77b7b601ccb1adf49c32e73b4332aba3` completed one full
run in `build/terminal_guest_v8`: all seventeen checks passed and the final
source/artifact verification succeeded. Producer system `fe9bf5f54da772cd`
and test system `31ae0eb6d1c5d02a` keep distinct full identities. Each binds
2,325 source inputs; their complete native SDKs were checked independently,
and all 190 actually used native compilation inputs match byte for byte.
The C SDK's 387 source inputs and 1,113 artifacts, plus the shared runtime's
473 source inputs and nine artifacts, were reverified unchanged before reuse
and again at qualification/export. The runtime keeps its original `e8817eeb`
producer identity and built-not-run receipt.

Both ordinary rounds and the native budget/rollback checks passed. Each
ordinary case restored exactly 129369 free pages, three processes and one
completion record. The six positive cases observed successful exec to their
validated new-main marker in 2.56–3.84 seconds, within the existing
thirty-second generation budget. Their aggregate supervisor packet waits
were 3.81–5.37 seconds. These are measured samples, not a general latency
guarantee. No production deadline or exact cleanup predicate was relaxed.

The calibration and actual owner-exit phases each began with a separately
formatted/populated disk. Their pre-nonce disk hashes match exactly; their
fresh random nonces differ. Both persisted complete 1,224-byte version-2
reports and matching witnesses after successful Files sync. Four actual QMP
samples, two per phase, each showed exactly 129553 free pages, two processes
and zero global completion records. Both native page/process observations,
all ten native final-state comparison fields and both global tuples match
exactly. The final observer has one thread, 369 user pages, one kernel-stack
page, no independent pipe references or own thread results, and parent PID
zero. Both experiments returned a net 375 pages from their measured
pre-actor owner/observer baseline. The privileged process-statistics query
remained denied with its sentinel output unchanged.

The actual owner-exit evidence distinguishes owner PID 7, terminal actor 10,
dynamic parent 11, fork child 12 and observer 9. An authorized snapshot saw
the child in generation 1, waiting with one blocked thread, before the owner
exited. Its read returned EPIPE after 20 ms in this run, and both old TTY
tokens were rejected. The child retained its parent-owned native READY/ACK
pair, PID, authority, Files cursor and independent pipe. Its later exec
returned EIO during the terminal snapshot, before a new PREPARE; this is not
claimed as a new generation handshake after owner death. The parent reaped
the child and read the next byte from their shared Files description.

The report's channel counters retain their actual sys90 scope: the legacy
`endpoint.generic` IPC channels created through sys84/86, not the sys81 TTY
pairs or sys88 IPC-v1 table. Their zero values do not imply the owner lacked
TTY authority. Actual TTY ownership/revocation and global page/task/completion
cleanup have the separate observations described above.

The complete local report is
[`p1_k2_terminal_controller_20261128`](../reports/p1_k2_terminal_controller_20261128/README.md).
Its flat manifest covers 215 evidence leaves and has SHA-256
`6db049bb87e34a189eabd50bd29246fd3f26006c8d008fe0f620dbc0e64fc707`.
It retains all nine failed development guest runs, including the complete
calibration from `v7_pipe`, the original outer FatFs error log and the QMP
socket startup failure. No partial results are combined with the successful
run. A separate preparation invocation failed when the SDK could not resolve
external Git-worktree metadata; its original command and tool-returned output
are archived with their capture origin, without counting it as a guest run
or reclassifying it. The subsequent full reuse verification ran on the host
and compilation remained in the pinned SDK.

The qualification is the frozen public startup capsule-v2 GNU C composition,
with native descriptor startup v3. It is not rebound to the newer mainline
capsule-v3 profile. It claims normal TTY-owner exit, separate actor and direct
controller failure, and the explicitly measured cleanup. It does not claim
TTY-owner kill, COM1 recovery after bootstrap-owner exit, online libraries,
GNU worker success in this C-only closure, SMP or physical hardware. Global
plan/ABI/state updates and publication remain with the coordinating agent.
