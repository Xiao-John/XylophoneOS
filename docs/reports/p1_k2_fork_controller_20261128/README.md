# P1-K2 dynamic fork controller qualification

System `15362d9ea4b71917` and its exact packaged native SDK passed **13
actual QEMU executions** with the independently anchored public glibc 2.44 /
GCC 16.2.0 C runtime. Ten cases cover direct fork-to-exec, nested direct-parent
controllers, attenuated creation authority, explicit native-thread-profile
rejection and normal controller exit, each through xsh and dash. Two further
executions qualify independent dynamic pipe aliases, CLOEXEC, direction, EOF
before child exit, EPIPE, failed/successful same-PID exec and the bounded
8-object / 16-reference / 32-FD composition. The final case cancels the
controller with ESC and checks descendant cleanup. Every case restores
**129789 free pages / 2 tasks /
0 completions**.

The child uses a fresh authenticated pair owned by its direct parent. The
parent keeps its upstream pair. Native commit precedes the single offer send;
building receivers remain unable to receive IPC. The target also checks
constructor rejection, PID/TID and copied-versus-exec TLS, failed exec
preservation, Files shared cursors and parent ownership. Fork admission remains
closed after the native thread profile is enabled. This C-only closure has no
approved unwinder, so that test does not claim a successful GNU worker.

`guest.json` and its lossless serial transcript contain the target observations.
`qualification.json` binds the complete native source/artifact inventory, both
complete SDK identities, authenticated source inputs, the shared runtime,
approved controller and both generations. All final inputs and snapshots were
rechecked at export. Producer receipts retain their original built-not-run or
SDK-built status; this independent report supplies the guest observations.
`host.json` plus the two host logs record ten adapter groups, twelve malformed
offers and seven begin rejections in ordinary and ASan/UBSan execution.

Five failed development runs remain failed beside the final evidence. The
first exposed the forbidden pre-commit offer to a building receiver. The
second reached successful orphan completion but required an exact shell-prompt
prefix correction in the result parser. The third passed all ten fork groups
and the first independent pipe group before an aggregate five-second fixture
watchdog incorrectly combined failed exec, successful exec and I/O. That
aggregate was initially changed under an incorrect five-second exec-budget
assumption. Existing production exec and both generation startup budgets
are thirty seconds; only fork admission has a five-second limit.
`exec_timing.json` records observed full-call monotonic durations, checked
against the unchanged thirty-second generation budget, with a sixty-five-
second two-call-plus-I/O watchdog. Each fixture correction was followed
by a fresh system, native SDK, stages and approved launcher; no older receipt
was relabeled. The fourth run lost the child before its post-fork owner-death
marker when the controller exited immediately after enqueueing READY_ACK,
consistent with the documented interrupted-adoption boundary. The final
owner-death fixture first requires a child pipe acknowledgement after fork
returns, then tests controller death and surviving PID/FD state. It does not
claim that an enqueued ACK has necessarily been consumed. The fifth run
passed all ten fork/controller cases, then failed the mistaken five-second
exec duration assertion. The final runner explicitly verifies the existing
thirty-second field in both bound generation headers and prints measurements
before checking them; no production deadline was increased. Observed timings
are fixture evidence, not a new universal exec latency guarantee.

The terminal-actor protocol has its own implementation and owner-lifetime
tests, with target qualification still in progress. Console and Files stdio
in this report do not establish
terminal-actor operation. These results apply to the recorded single-core
QEMU x86-64 environment and fixed-startup GNU C closure.

Host source, execution-toolchain and SDK-producer toolchain locations use
explicit `${XOS_SOURCE}`, `${XOS_TOOLCHAIN}` and `${XOS_PRODUCER_TOOLCHAIN}`
templates in these derived reports. Original producer/input hashes remain
recorded separately; exported hashes are supplied only by the flat manifest.
