# P1-K2 independent terminal controller qualification

The explicit test system `31ae0eb6d1c5d02a` passed **17 actual target
checks** with a real COM1 terminal actor and the independently anchored public
glibc 2.44 / GCC 16.2.0 C runtime. Two rounds cover direct same-PID exec,
fork-to-exec with distinct TTY and launch owners, denied create authority,
normal direct-controller exit, explicit controller cancellation and actor
death/recovery. Native checks cover legacy four-channel versus explicit
six-channel admission, ownership and shape rejection, the cumulative IPC
budget, and cleanup when READY succeeds but ACK allocation fails. The normal
cases restore **129369 free pages /
3 tasks / 1 completions**.

This is the frozen **public startup capsule version 2** composition, with
fork controller production checkpoint `98311717` and final fixture checkpoint
`6b513fff`. Its native descriptor receiver opt-in is separately version 3.
The shared runtime was built from `e8817eeb`; every production input was
reverified unchanged against the qualification source. A newer capsule-v3
source/SDK/runtime composition needs its own qualification. These records are
not rebound to that newer profile or to another integrated mainline build.

The GNU fixture exercises an authenticated terminal session before initial
READY, terminal I/O and termios, failed exec preservation, actual image
replacement with the same PID, copied then reinitialized TLS, Files aliases
and shared cursor, pipe data and EOF, and terminal/File/pipe CLOEXEC behavior.
A child acknowledgement after fork separates completed adoption from the
controller-exit case. The direct parent's launch-control pair and the
supervisor's TTY pair have independently tested lifetimes. Root-application
exit retains the existing actor policy of ending its foreground group.
The child therefore checks revoked TTY tokens and EPIPE while preserving
ordinary PID/authority/Files/pipe state; the supervisor still uses the actor.

All six positive cases provide monotonic timing observations. Successful
exec to the validated new-main marker ranges from
2.56 to
3.84 seconds. The
actual generation's startup field remains thirty seconds. The supervisor's
sixty-five-second aggregate watchdog covers fork, failed exec, successful
exec and post-exec I/O; it does not replace their individual protocol bounds.
The resource cleanup deadline remains five seconds. These samples do not
establish a universal full-call exec latency guarantee.

The final cold-boot experiment uses five distinct processes: the genuine
bootstrap TTY owner, its terminal actor, a dynamic controller, a fork child,
and a device-free observer. Native observation proves the child is blocked in
a real terminal read before the TTY owner exits normally. The child receives
bounded EPIPE, rejects its old terminal tokens, preserves its separate launch
controller pair, and rejects an exec requiring that lost terminal with EIO
while keeping PID, authority, Files and pipe state. This rejection happens
during the terminal snapshot, before a new exec PREPARE is sent. It proves
survival of the existing native launch pair, not a new generation handshake
after the TTY owner exits. The controller waits its
child and observes their shared file cursor. The observer writes a nonce-bound
1,224-byte version-2 report and a separate witness after the report's successful Files
sync. The host stops QEMU before cold-reading both files.

Each cold phase begins with a newly formatted private FAT32 disk populated
from the same bound payload. The two pre-nonce disk hashes match exactly;
each phase then imports its own distinct random nonce, with no inherited
report or witness. The normal run's final disk hash and all cold-phase
input/output hashes remain evidence. Disk images containing different
nonces are not required to match.

A separate calibration boot uses the identical observer ELF with no actor or
dynamic application. After owner exit, the actual and calibration boots match
exactly: **129553 free pages / 2 tasks /
0 completions**, together with the observer's user/stack
pages, owned channels and pipe references. The evidence retains the departed
owner's measured page/object account and both net page returns. The private
report's channel fields retain the existing sys90 resources counter for
`endpoint.generic` channels. That counter excludes sys81 terminal pairs;
its zero value does not say that the departed owner had no TTY authority.
TTY ownership and revocation are established separately by native channel
information, five distinct process identities and rejected old tokens. This proves
normal TTY-owner exit; it does not claim owner kill or COM1 recovery after that
owner exits.

The ordinary observer explicitly proves that the supervisor-only statistics
query remains denied without writing its sentinel buffer. Checked existing
thread statistics provide its own thread/page accounting and the native
global process/page counts; self observation authenticates its parent,
channel and pipe state. Its own thread results are separately named and are
not used as global completion evidence. For the latter, the host binds the
exact kernel ELF, source declarations and sized symbols, then performs two
read-only QMP stop/read/resume samples after the final two bounded pumping
intervals. Both samples require two processes and zero used completion slots,
match the native page/process observations, and match the independent cold
calibration. Complete commands, symbol output and raw memory bytes accompany
the reports. No guest privilege or memory write is introduced.

The producer and test system retain distinct complete identities. Their
native headers, CRT, linker script and archives actually used by the
supervisor are compared byte for byte. `qualification.json` records both
complete source/artifact inventories, both native SDK identities, the C SDK,
shared runtime, approved generation, controller and supervisor receipts.
All final inputs and complete snapshots were reverified at export. Producer
receipts keep their original built-not-run status; `guest.json` supplies the
independent target observations. Embedded producer and sampler binding hashes
refer to original inputs before mechanical path redaction; the flat root
manifest separately verifies these exported bytes. Lossless serial transcripts and lossless hex encodings of the raw cold
receipts accompany the reports; each encoding retains its original input hash. Focused ordinary and ASan/UBSan host fixtures
model production validation, registration and fork boundaries; they do not
substitute for the target checks. A further 32 groups run in both ordinary
and ASan/UBSan modes for the transport-invalidation fix, covering close
races at wait/send/receive, explicit denied replies and fork registration
cleanup without retry. Only exchange transport invalidation becomes the
existing broken-stream result; initial authentication, valid denied replies,
timeouts, interruption and malformed replies retain their distinct errors.
The sampler additionally passed 31 host checks in both ordinary and pinned
SDK environments using the actual kernel ELF and modeled QMP transport;
the two final cold boots supply the actual QMP observations.

The first actual guest remains failed after passing channel admission and
its first direct/fork/authority cases. Its owner-exit test assumed orphan TTY
continuity contrary to the pre-existing root-session lifetime. The current
fixture requires foreground revocation and independent FD/PID preservation;
its corrected contract does not expand that lifetime.

Development v2 passed all thirteen ordinary checks before a generic resource
comparison failed. Diagnostic v5 again passed those checks and identified the
partial launch-pair boundary: its prematurely captured actor baseline had
136 more free pages than the post-rollback state. All other resource fields
matched, and the observed state exactly equaled the normal stable actor
baseline. The final fixture completes an authenticated actor roundtrip before
taking that baseline. It retains exact resource equality, the five-second
deadline and final IPC usage of two. The budget marker also uses that visible
control channel. Both original failed runs and their full transcripts remain.

Diagnostic v3 and an independent repeat stopped after a fork child's
failed-exec marker, at different repetitions. The old ten-second aggregate
watchdog covered a composition whose generation permits thirty-second
startup. Fatal supervisor writes while the foreground worker is attached can
also be denied by the existing actor policy, so missing failure text does not
prove an infinite controller poll. The final fixture uses the explicit
aggregate budget and records both new-main and completion timing. Those
changes are not presented as a proven retrospective cause of the two old
stops; both failed records are preserved. Diagnostic v4 separately failed in
the newly added host parser before its per-case output existed. The parser
now waits for the complete current case, and the supervisor prints its timing
after detach and resource recovery. These corrections do not change a
production timeout or error policy.

Development v6 passed all fifteen ordinary/native checks, then its calibration
observer timed out after the convenience statistics wrapper discarded a
supervisor-only permission denial and returned zeros. The nonce-matching
version-1 failure report was written without a success witness. That original
failure remains intact. Version 2 checks syscall errors, preserves the denied
permission, uses the existing readable statistics, and obtains independent
global completion proof through the host sampler. It does not infer cleanup
from the old failed loop or widen the observer's authority.

The first complete version-2 attempt, v7, again passed all fifteen ordinary
and native checks. Its calibration QEMU exited before boot because the
environment refused a Unix-domain QMP socket. The original failed report and
QEMU stderr remain evidence. A full repeat selected the existing private
FIFO QMP transport inside the SDK command environment. It passed sixteen
checks, including the actual calibration with two matching QMP samples,
then failed before the actual owner-exit boot: the create-new disk importer
refused a second nonce at the existing path with FatFs result 8, FR_EXIST.
That full failed repeat, its calibration evidence and the wrapper log with
the actual FatFs error remain preserved. The final fixture starts each cold
phase from an independently populated disk. Its source and native system
were rebuilt and bound anew, while the complete unchanged C SDK/runtime
inputs were reverified before reuse. All seventeen final checks belong to
that one complete FIFO-transport run; partial results from different runs
are not combined into its qualification.

A separate build-preparation invocation also failed before starting a native
build: its SDK container could not resolve the external Git worktree metadata
for the reuse check's HEAD query. The original command and tool-returned error
are archived with that capture origin stated explicitly. The complete
read-only source/artifact and HEAD verification subsequently ran on the host,
while native compilation remained inside the pinned SDK. This preparation
failure is not a guest attempt and is not reclassified as successful.

The first supervisor link was rejected at 139,064 bytes by the unchanged
128-KiB native image bound and remains failed. Its explicit test recipe now
removes only nonallocated symbol tables. It compares every program header,
loaded byte and allocated section, including BSS layout and startup-v3
metadata, before and after stripping. The resulting standalone supervisor is
123,784 bytes. This qualification does not increase the
native image limit, grant a new device permission, or silently change the
ordinary four-channel API.

This report is separate from fork/controller migration and independent pipe
qualification. Its results apply to the recorded single-core QEMU x86-64
fixed-startup GNU C composition.
