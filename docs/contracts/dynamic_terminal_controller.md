# Dynamic exec with an independent terminal actor

The public GNU dynamic profile can use the existing authenticated terminal
actor protocol together with its READY/ACK launch controller. The terminal
actor remains a separate process. Its channels, owner and sequence belong to
the terminal protocol; the launch controller continues to authenticate image
generations, PREPARE, READY and failure. The two pairs never substitute for
one another.

This contract is separate from
[dynamic fork controller migration](dynamic_fork_controller.md). The ordinary
`dynamic-run` console/Files controller does not become a terminal supervisor.
An authorized native supervisor explicitly supplies `prepare_child` and
`terminal_send_handle`, attaches the prepared application to its real actor,
and installs an approved dynamic policy through the existing SDK.

## Explicit bounded channel composition

The supervisor normally owns two actor-control channels and two application
channels. Composing a READY/ACK pair requires six owned one-way channels.
`sys_channel` (81), action 7 `create_extended`, accepts the existing 32-byte
version-1 `channel_create`. Both its reserved field and syscall argument 3
must remain zero. It applies a six-channel owner limit. Action 0 `create`
keeps its four-channel limit and never inherits the larger allowance from a
previous extended call. The existing fork-pair mechanism keeps its total
eight-channel owner limit.

`sdk::channel_open_extended` selects action 7 explicitly. The last parameter
of `launch::record_child` is `extended_channels`, defaulting to false. Only
the dynamic spawn adapter's explicit terminal startup composition selects it.
Ordinary launch registrations and fork controller migration keep their
existing selection. A failed second channel creation closes the first before
returning an error; it does not install a partial registry entry.

The extension changes no PID control rule, channel direction, ownership,
global endpoint pool, cumulative process budget or cleanup rule. It grants no
process creation, terminal, device or image authority. Validation precedes
allocation, and the existing budget admission still runs for each endpoint.
Old kernels reject the new action. A matching rebuilt kernel and SDK are
required; there is no fallback that silently widens legacy creation.

## Startup and replacement

The dynamic bootstrap already declares the native `.xos.tty` marker and
consumes the existing startup terminal extension. A new v3 descriptor startup
with terminal FDs now initializes that extension's terminal sequence to one,
the sequence of the newly attached actor session. This makes an explicit
initial FD snapshot compose with terminal startup. The wire layout does not
change.

Terminal replacement accepts either the existing two terminal channels, or
four channels consisting of the terminal pair followed by the dynamic
READY/ACK pair. The loader validates the complete selection before creating
the replacement:

- Handles are nonzero, unique and visible in native channel enumeration.
- Each pair has one send endpoint and one receive endpoint with the same
  peer and controller identities.
- The advertised terminal-send handle is the send endpoint of the first
  pair; its actor peer differs from its owner.
- In the four-channel form, the last two endpoints have READY-send and
  ACK-receive directions, and their peer is their launch controller.
- The terminal sequence is nonzero and every metadata record has the
  expected version and size.

The terminal owner need not equal the launch controller. For example, after
fork the terminal pair can remain owned by the original supervisor while the
child's launch pair belongs to its direct parent. Native endpoint membership
supplies authority; copied handle numbers cannot pass this validation.

Successful replacement uses the existing `sys_process_exec_commit` (60)
bit-32 preservation entry, whose maximum remains four channels. PID and
channel identities survive; the terminal sequence continues. GNU TLS starts
with the new image's initialization, and ordinary FD aliases, shared Files
offsets and CLOEXEC behavior retain their existing rules. Failure before
commit preserves the old image and descriptors, releases temporary snapshot
references, and cancels any pending image admission through the existing
launch protocol. No ownership-changing request is automatically replayed.

## Independent failure and cleanup

An actor death revokes its terminal endpoints. The terminal client reports
the existing stream error and invalidates its local actor session. The
process, independent Files/pipe FDs and its launch-control pair remain under
their own lifetimes. A later exec which still needs terminal FDs cannot
pretend that the invalid session is usable.

An exchange using an established terminal session maps native transport
invalidation (`-1` from wait/send/receive) to the existing broken-stream
result (`-7`, GNU `EPIPE`), closes both endpoints and discards the local
session. It does not replay the request or reconnect: an interrupted write
or registration may already have executed. Initial connection or startup
authentication denial retains its existing error. A complete authenticated
service reply carrying denial or interruption remains `EACCES` or `EINTR`;
timeouts and malformed replies keep their own errors. A later operation on
the cleared session retains the existing invalid-session `EIO` result.

A direct launch-controller death revokes that controller's pair. The
terminal actor also retains its existing foreground-group policy: when the
root application exits, the actor closes that group's derived child sessions
even if the TTY owner and actor processes remain alive. Surviving children
retain independent Files and pipe I/O and their PID/authority, but lose the
foreground terminal and cannot obtain further replacement admission from
their dead controller. The supervisor can continue using the same actor
after detaching the ended group. Normal parent exit sends runnable children
to the kernel reaper. Explicit cancellation follows the existing descendant
cancellation ancestry and reclaims their channel, file and pipe references.
The post-adoption controller-exit fixture first receives an independent pipe
acknowledgement sent by the child after `fork` returns. A controller lost
while its READY_ACK is still in flight can instead interrupt adoption with
child status 127, as specified by the separate fork protocol.

The native caller owns terminal detach/close if construction fails after its
`prepare_child` callback has attached the application. Dynamic controller
registration cleans up its own partial pair independently. This separation
also applies when a cumulative IPC budget allows the first new launch
endpoint but rejects the second.

## Qualification and reproducible test construction

The dedicated target fixture is an explicitly selected supervisor with
compile-time approved generation roots and an actual COM1 terminal actor.
Its program uses the public GNU runtime. The recorded target cases include direct
exec, fork-to-exec with different terminal/launch owners, create-authority
rejection, actor death, controller exit/cancellation, exact FD/PID/TLS rules,
native action-0/action-7 limits and cumulative-budget rollback. The host
fixtures exercise production validation and launch registration at modeled
native boundaries; they are not target qualification.

The test build has two complete, distinct system identities. A producer
system supplies the exact native SDK used to compile the program bootstrap
and approved supervisor. The explicit test system then embeds that verified
supervisor ELF. Every used native header, CRT, linker script and archive is
compared byte for byte across the two SDKs. Their full manifests, tree hashes
and build IDs remain separately bound. A deterministic build-directory prefix
map keeps native archive debug paths independent of the chosen output
directory; no receipt or old artifact is modified to force a match.

The shared GNU runtime, complete C SDK snapshots, approved generation,
supervisor producer, both system manifests, terminal actor ELF and test input
files are verified before and after the guest run. Actual results, including
any failed development attempts, belong in the accompanying work record and
report. This contract does not claim a normal shell terminal launch path,
unapproved image loading, arbitrary channel counts or successful GNU worker
creation in the C-only fixture.

## Distinct owner lifetimes in qualification

The fixture distinguishes termination of the actor service, termination of a
direct dynamic controller and termination of the owner of the TTY channels.
For the last case the genuine bootstrap owner exits normally while a GNU
child is already blocked in an authenticated actor read and its separate
dynamic parent remains alive. Authorized native observation establishes the
blocked state before exit. A device-free observer records the resulting
bounded EPIPE, stale terminal-token rejection and failed-exec identity/FD
preservation through independent pipes and a synced Files report. The host
checks the report only after stopping the VM, including a fresh random nonce.
A separate cold-boot calibration measures the same surviving observer and
Files process, so exact page/object reclamation does not assume the departed
owner still exists. This fixture adds no device delegation and claims no
owner-kill or COM1 recovery after bootstrap-owner exit.

After the pending read invalidates the local terminal session, the observed
failed exec stops during the terminal snapshot with EIO, before sending a
new PREPARE. The case proves that the existing parent-owned READY/ACK pair,
PID, authority, Files and pipe state survive and that the parent can wait and
reap its child. The ordinary direct/fork cases independently prove successful
exec; the owner-exit case does not claim a new generation handshake after the
TTY owner disappears.

Each cold phase formats its own private FAT32 disk and imports the same bound
program/runtime/input payload before adding that phase's new random nonce.
No prior nonce, report or sync witness is carried into the next phase. The
normal experiment's final disk hash and each cold phase's payload, input and
output disk hashes remain recorded. Raw disk hashes need not match between
phases containing different nonces; the resource comparison remains exact.

The observer is an ordinary spawned process. Its checked call to the
supervisor-only process-statistics operation must remain denied and leave its
output unchanged. Existing thread statistics provide the global process and
free-page counts and its own thread/page accounting; authorized self
observation supplies parent identity, channels and pipe references. The
private version-2 evidence format names thread results separately from
process completion records.

Its channel fields also retain the precise scope of the existing sys90
`owned_channels` counter: channels marked `endpoint.generic`, created through
the sys84 endpoint and sys86 naming interfaces. The counter does not count
sys81 TTY pairs or the independent sys88 IPC-v1 table. TTY ownership and
revocation are proved separately by native channel information, distinct
process identities and rejection of the old TTY tokens.

Global completion cleanup is independently checked by the host through
read-only QMP memory samples. The sampler binds the exact kernel ELF, source
definitions and sized symbols for the task count, physical free-page count
and sixteen completion records. After the native experiment, it pauses the VM,
saves only those bytes, and resumes it. Two samples must agree exactly, show
two surviving processes and zero completion records, and match the observer's
native process/page counts. Both cold boots must then have the same global
and observer resource states. The sampling adds no guest authority and makes
no memory writes; its commands, symbol layout and raw bytes remain evidence.
