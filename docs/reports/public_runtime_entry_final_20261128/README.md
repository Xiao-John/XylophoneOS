# Public GNU runtime: ordinary entry qualification

The exact native system `faad61f4f20be0f7` passed all **8**
ordinary public-runtime cases. Every command returned the expected successful
completion and restored the same physical-page/process/completion baseline.
The production native controller used explicitly compiled approved generation
roots, ordinary SDK inspect/spawn/wait, transferred readonly file pins and the
actual GNU interpreter. The runtime was built by the public GNU `make lib`
path; no private `rtld-routines` substitution supplied this execution.

| Case | Round | Wall seconds | Result |
|---|---:|---:|---|
| c-basic | 1 | 3.751 | passed |
| c-policy | 1 | 3.567 | passed |
| c-spawn | 1 | 5.521 | passed |
| c-exec | 1 | 5.626 | passed |
| cpp-xsh | 1 | 10.883 | passed |
| cpp-dash | 1 | 10.586 | passed |
| thread-xsh | 1 | 10.799 | passed |
| thread-dash | 1 | 11.43 | passed |

This is one complete round from the frozen public source checkpoint
`299ea47cc991fb781e8671c41213a02c169f4130`. All eight cases restored exactly
129678 free pages, 3 processes and 1 completion record. All **3341** bound
inputs were verified before and after execution and again before export.
The final run used the coordinated QEMU window after the final R2 guest
closed and before the release candidate's smoke/installer/stock pipeline.

| Bound component | SHA-256 |
|---|---|
| Native SDK manifest | `fc8b81adef3b0397bb7743093091ffc21d07f14c6a33504e1d087d11e8601ffa` |
| Native SDK complete file tree | `25c705d9e1388330db72d75ca1c22e129fe7a330a7810c9afedd49fdd5ebdde6` |
| C SDK manifest | `59e9daf663168bb591479434f373ad9616e19b8dab155d6a2c1a1d461d4aa95a` |
| C SDK complete sysroot tree | `a1109d8caad10d6a921aeae9d74ed4e3d8e648b3cf3c9adc7c5f4c9edce12a31` |
| Native dynamic ABI identity | `6742293901e0c560b8232b7c29ec44e13348e03903942ac8e1c387a0ac92111d` |
| Approved-root native launcher | `0fd31788992306cf779003b259fae31b3ba1e8d3c9519fe9ae6761be76cc8a5d` |
| Final static dash executable | `f4193dcecdd2d1037d7baf4770b90e30cdc9ee26180faea1a5a95995abf1b1e5` |

The C cases cover constructors, TLS, relocation, environment, explicit runtime
dlopen/dlmopen/dlclose denial, inherited FD aliases/shared cursors, CLOEXEC,
ordinary posix_spawn with authenticated readiness, failed exec cancellation
that retains the old process, and successful same-PID image replacement.
The spawn case checks that the main executable's constructor has finished
before posix_spawn returns, using a constructor-created completion file.
The C++ cases exercise actual shared GNU libstdc++/libgcc/libm, a separately
linked C++ DSO, cross-DSO exceptions, RTTI, unwinding, TLS teardown, atexit,
std::thread move/join and isolated application/DSO thread-local state. C++ and
thread programs enter through both ordinary xsh and dash commands. The outer
dash is a separately bound static-libc baseline; it is used as a shell entry,
not represented as a build of the tested shared libc.
This final round uses the newly built final static dash and its final
application-SDK profile and build receipt. The older dash remains only in
the independently preserved historical attempt and diagnostic evidence.

The thread executable also creates and joins a real worker inside its main
program constructor. This exercises the internal already-loaded unwinder
lookup before the initial READY. Readiness is sent once by shared libc
after both constructor phases; later internal initialization must not
replay it. Controller authentication and replay rejection stay strict.

The sequential ELF-metadata parser preserves the 30-second absolute startup
budget. Each entry's wall time includes controller installation, any requested
activation, inspection, launch, native/GNU startup and final completion; it
is not a claim that these independent controller operations share one deadline.

`guest.json` binds the complete native/C SDK identities, immutable system and
runtime sources, producer receipts, application bytes, compiler/interpreter
inputs and actual commands. Inputs were checked before and after execution,
and again at export. Build receipts retain `built_not_run`; this separate
guest report records execution instead of modifying historical producers.
The flat root manifest covers all exported leaves and git authenticates it.
`conversion.json` preserves raw report identities and records mechanical
environment-path substitution. `${XOS_WORKSPACE}` is the explicitly selected
development workspace; `${XOS_ROOT}` is this checkout. The Preview2 prefix,
Cellar and temporary-root templates identify that pinned SDK environment.
The Preview2 tools template identifies its selected compiler-wrapper root.
Within the recorded guest shell commands, `${XOS_GUEST_TESTS}` means `/tests`
and `${XOS_GUEST_APPS}` means `/apps`; those templates are never applied to
host source paths or artifact identities. Serial output preserves guest paths.


## Preserved earlier attempts

Earlier reports and serial logs retain their original source, SDK, artifact and outcome bindings. They are not qualifications of this later build.

- Attempt 1: `failed`, system `c1575e2adfc6fa5d`, 6/7 recorded cases passed; unsuccessful cases: thread-xsh.

## Scope

Approval and activation remain bounded per-controller volatile state. This
matrix does not qualify durable global catalogs, power-loss recovery, online
library loading, cross-descendant revocation, dynamic fork-to-exec controller
migration, terminal-actor dynamic exec, or the dynamic-libc/DHCP combination.
The constructor observation uses the supported public monotonic clock and
sched_yield; it does not qualify nanosleep or clock_nanosleep, which remain
outside this completed startup/FD/exec/thread scope.
The final R2 generation-transition evidence and static R1 SDK qualifications
are separate reports with their own exact source and artifact bindings.
