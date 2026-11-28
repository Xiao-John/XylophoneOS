# Public GNU runtime: ordinary entry qualification

The exact native system `eeb192efd1422062` passed all **9**
ordinary public-runtime cases. Every command returned the expected successful
completion and restored the same physical-page/process/completion baseline.
The production native controller used explicitly compiled approved generation
roots, ordinary SDK inspect/spawn/wait, transferred readonly file pins and the
actual GNU interpreter. The runtime was built by the public GNU `make lib`
path; no private `rtld-routines` substitution supplied this execution.

| Case | Round | Wall seconds | Result |
|---|---:|---:|---|
| c-basic | 1 | 3.503 | passed |
| c-policy | 1 | 3.684 | passed |
| c-spawn | 1 | 5.804 | passed |
| c-exec | 1 | 5.875 | passed |
| c-pipe | 1 | 10.933 | passed |
| cpp-xsh | 1 | 10.421 | passed |
| cpp-dash | 1 | 11.702 | passed |
| thread-xsh | 1 | 10.813 | passed |
| thread-dash | 1 | 12.432 | passed |

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

The thread executable also creates and joins a real worker inside its main
program constructor. This exercises the internal already-loaded unwinder
lookup before the initial READY. Readiness is sent once by shared libc
after both constructor phases; later internal initialization must not
replay it. Controller authentication and replay rejection stay strict.

The additional dynamic C pipe case uses the public posix_spawn API
within its own approved GNU closure. It checks real pipe reads and writes,
shared status flags across stdio and extra-FD aliases, CLOEXEC exclusion,
a second-generation spawn retaining a read alias after fd0 closes, a retained
write alias after fd1 closes, last-close EOF while the child remains alive,
explicit rejection of unrouted pipes without changing the parent's endpoints,
and EPIPE after the last reader closes. This is a real dynamic execution;
the separately recorded finite static loader override is not reused as its
qualification.


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



## Scope

Approval and activation remain bounded per-controller volatile state. This
matrix does not qualify durable global catalogs, power-loss recovery, online
library loading, cross-descendant revocation, dynamic fork-to-exec controller
migration, terminal-actor dynamic exec, or the dynamic-libc/DHCP combination.
The final R2 generation-transition evidence and static R1 SDK qualifications
are separate reports with their own exact source and artifact bindings.

## Final composition and history

This is one complete round against frozen source
`08c97e1c9a9f3ee4a03cae24ad02214809786782`. All **3352** input bindings
were checked before execution, after execution and at export. Every case
returned to exactly **129678 free pages / 3 processes / 1 completion**.

- Native SDK manifest: `3a4f8a084a0c3ef288ee2d18aeb418c82ff936cec0be637b892b9c0bdc88c5e1`.
- Native SDK file tree: `c3e3a21dbf953dc680f7e4ad693133ef4f93fe3cbf4b564072a2b5fe94d93c19`.
- C SDK manifest: `737c00f7a6ca7e16d93fc2b0e3057ac1bb6fdfef46f8273a225cdfcd435cefc1`.
- Complete C SDK sysroot tree: `27d2c45b8f6c64fc1a0a7cd54e858577cab7f1a595b62dbfd9f63c866f616466`.
- Final static Dash ELF: `af287dddcb2dfcaf5aed20a6547e06579035da9b38225c60c191b87f19092df1`.
- Final static Dash producer receipt: `9bbd53da21ec5160900992c815d7a4da585ecd4ca97b660e3f615f245642cd06`.
- Raw guest report: `25681c6cd27fd160f39893a99afc5c8a06473faeab9f76d911e536a782acc923`.

The preceding eight-case composition remains recorded separately. Its later
release-candidate daily-tools pipeline exposed a real pipe-token transfer
failure. The ordinary v3 loader was corrected and the native SDK, C SDK,
public GNU runtime, shared GCC libraries, four applications and launcher were
rebuilt. This report qualifies those new bytes and adds the dynamic pipe
case; it does not change the identities or results of the prior composition.
The [separate SDK archive report](../public_spawn_pipe_sdk_final_20261128/README.md)
qualifies the same production loader through the delivered static support
archive, without a diagnostic object override.

The native routing bound is one input and two output routes. The 32-entry
FD snapshot supports aliases and Files descriptors within that bound;
unrouted independent pipe objects are explicitly rejected. Arbitrary pipe
token transfer and additional independent routes remain future work.

## Serial evidence review

The complete 11,594-byte, 322-line serial stream was read before publication.
It contains only the self-built QEMU guest's compiled boot banner, synthetic
kernel checks, guest test commands, application markers and resource counts.
The banner text is present in `src/kernel/core/console.cpp`. It contains no
host paths, host file contents, credentials or captured network payloads.
The recorded QEMU invocation uses `-nic none`.

The original serial SHA-256 is
`8302b1fe584c56f2d8dc6c254fa75aefb474c7a66895ff1a335f7d47a153a6ea`.
`serial.log.gz` is a byte-exact compressed copy, with SHA-256
`fe5e8cbb523df3de73b58711558f917e153c06998023ab28657ec91247b212da`.
