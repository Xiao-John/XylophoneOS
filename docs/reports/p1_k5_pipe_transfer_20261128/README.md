# P1-K5 independent pipe-transfer qualification

System `fed3580022aa4bb3` and the freshly built, authenticated glibc 2.44 /
GCC 16.2.0 SDK passed **16 actual guest executions**. Six native groups ran
twice, followed by both GNU probes through xsh and a dash rebuilt from the
same SDK. Every run restored **129789 free pages / 2 tasks /
0 completions**. GNU executables linked the matching production SDK
archives; no loader object was overridden.

The six native groups cover full request validation and authority, a 144-byte
output crossing into a read-only page, exclusion of fork/replacement-pending
children, capacity and original-domain budget charge, a post-transfer loader
callback failure, and an actual child using granted private tokens while
rejecting a known ungranted token and the wrong I/O direction. The capacity
case first fills 16 references using 3 stdio routes plus 13 private tokens,
checks atomic rejection, retires the routes, then successfully retries the
remaining 3 tokens. Parent close does not return the 8 object credits until
the child's final references are destroyed.

The GNU probes preserve fixed-route behavior and exercise independent aliases,
shared status flags, CLOEXEC exclusion, EOF after last close while the child is
still alive, EPIPE, failed exec preserving the original process, successful
same-PID exec, and 8 objects / 16 endpoints / 32 FDs including 13 extra aliases.
The old unrouted-pipe rejection case is updated to actual independent transfer;
the native default-false option still has a separate rejection assertion.

`guest.json` and the lossless `guest_serial.log.gz` record the target results.
`qualification.json` binds the complete current system and SDK source/artifact
inventories, tools, authenticated source, exact probes and original raw receipt
hashes. All bound inputs were rechecked after execution and at export. Producer
receipts remain `built_not_run` / `static_sdk_built`; this independent report
supplies the guest observation. The flat manifest binds every exported leaf.

The first development run passed five native groups, then exposed a fixture
expectation error: the existing native I/O contract returns denied for an
unowned token or wrong direction. The corrected test and six-group rerun are
retained alongside the failure transcript. The final system was rebuilt after
that correction, so the original development image is not the final acceptance.

The [contract](../../contracts/independent_pipe_transfer.md) defines sys34's
explicit mode, its 144-byte v1 request, complete-batch atomicity and unchanged
16-reference / 8-object bounds. This report qualifies native SDK and static GNU
execution on the recorded QEMU x86-64 environment. It does not borrow static
results as shared dynamic-runtime, SMP or physical-hardware qualification.
