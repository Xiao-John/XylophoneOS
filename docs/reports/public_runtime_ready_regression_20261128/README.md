# Public runtime: constructor readiness and internal unwind regression

The final v4 ordinary-runtime attempt is preserved as a **failure**. With
native system `c1575e2adfc6fa5d`, it passed six cases: ordinary C startup,
explicit runtime-loading denial, posix_spawn and FD inheritance, same-PID
exec, and shared C++ exception/RTTI/unwind entry through xsh and dash. The
seventh case, `thread-xsh`, exited 127 with `startup controller rejected
READY`; `thread-dash` did not run. The capsule/worker-arena collision had
already been corrected in these exact bytes.

The source analysis found that the previous hook announced READY at every
`_dl_init` invocation. GNU's internal already-loaded unwinder lookup can
invoke that path again. The controller correctly rejected the second
READY. Also, this loader phase precedes the executable's own constructors;
those run later in the shared libc initial entry.

Commit `786b051b` moves the public READY notification to shared
`__libc_start_main`, after both the DSO and main-executable constructor
phases and immediately before `main`. It uses the libc's already validated
startup descriptor and artifact, and still waits for authenticated ACK.
The rtld retains its failure notification; no controller authentication,
replay rejection, deadline or admission rule is weakened.

## Independent diagnostic execution

`diagnostic_guest.json` records the actual finite relink and three real
guest regressions performed before the next full SDK rebuild. The test
copied the actual GNU archives, compiled the changed libc-start/dl-init
and native spawn/control objects, checked that every other archive member
and its order remained unchanged, and ran the real GNU partial/final
links. Original v4 source, objects, archives, ELF files and receipts were
not overwritten. New C and thread executables, generation manifests and
an approved-root production launcher were then built and preflighted.

| Diagnostic case | Wall seconds | Result |
|---|---:|---|
| Constructor completion before parent posix_spawn returns | 5.552 | passed |
| Real constructor and main std::thread through xsh | 12.001 | passed |
| Real constructor and main std::thread through dash | 11.379 | passed |

The C constructor yields against the public monotonic clock for 100 ms,
then creates and closes a completion file. The parent must observe its
complete contents immediately after posix_spawn returns and before waiting
for exit. The C++ executable creates and joins a real worker from its
main-program constructor, then exercises the existing main worker's TLS,
DSO TLS, exception handling, move/join and application/DSO TLS destructors.
Both shell routes emit all required markers and exit successfully. Every
case restores the observed baseline of **129680 pages, 3 processes and 1
completion record** exactly. This is the same startup baseline as the
preserved v4 attempt, not the separate R2 fixture's baseline.

The new unstripped diagnostic libc digest is
`f2cb833407e295843c15494d77a89622b91783f0a4ed8435933a589394fbeb15`;
the new interpreter digest is
`b5ca1585ab1d287fe2229712290ed907198e859e61cf6b687fa4e0843d3ee00d`.
All installed payload digests, generation roots, commands, tool identities,
source/include dependencies and 878 bound inputs are retained. They were
verified at the end of execution and again before export. The probe and
corrected public-clock test are committed in `3d5b1e88`.

This is a deliberately limited **diagnostic**, with
`qualification_transfer=false`. It reuses unchanged v4 support objects and
the c157 native SDK to isolate this concrete regression. It is not a new
SDK producer, does not qualify the later integrated source snapshot, and
does not replace the full eight-case R3 matrix or the independent R2
three-round qualification. The next native/C SDK, GNU runtime and shared
C++ production composition must be rebuilt and run with their own hashes.

Two earlier local diagnostic harness attempts are also retained in the
working output: the first used the profile's unimplemented nanosleep stub
and its test constructor exited before READY; the second incorrectly
assumed a two-process idle baseline and stopped before any runtime case.
Neither is counted as passing. The final test uses already implemented
CLOCK_MONOTONIC and sched_yield and compares the observed before/after
resource baseline without changing production behavior.

The original v4 run overlapped the root R1 candidate's QEMU pipeline for
part of its execution. It is not described as an exclusive-QEMU run. The
independent successful diagnostic ran after those guests had closed.

`conversion.json` preserves raw report and serial identities. Only known
environment roots were replaced with explicit replay templates. Guest
`XOS_GUEST_TESTS` and `XOS_GUEST_APPS` templates apply only to recorded shell
command fields. Raw serial observations and artifact/source digests remain
unchanged. The flat manifest covers every exported leaf.

GNU relative input/include paths in the diagnostic command records are
resolved against each recorded working directory before template conversion.
This preserves their execution meaning and avoids interpreting a relative
include suffix as an absolute host path. The raw report hash remains recorded.
