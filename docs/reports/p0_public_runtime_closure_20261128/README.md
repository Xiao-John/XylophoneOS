# Current public GNU runtime closure

The fresh Preview 2 composition passed all **nine ordinary public-runtime
cases** on native system `ec96cc19110d9906`. Every case restored exactly
**129693 free pages / 3 processes / 1 completion**. All **3352** bound inputs
were rechecked after execution and again before this summary was generated.
No production correction was required by this run.

| Case | Wall seconds | Result |
|---|---:|---|
| c-basic | 4.433 | passed |
| c-policy | 4.674 | passed |
| c-spawn | 7.279 | passed |
| c-exec | 6.762 | passed |
| c-pipe | 16.116 | passed |
| cpp-xsh | 14.771 | passed |
| cpp-dash | 13.307 | passed |
| thread-xsh | 13.3 | passed |
| thread-dash | 17.296 | passed |

The C cases used real GNU startup, constructors, TLS, relocations and the
authenticated READY/ACK path. They required explicit online loader denial,
ordinary spawn with aliases/shared cursors/CLOEXEC, failed-exec preservation,
and genuine same-PID image replacement. The C spawn case checked main-program
constructor completion before READY.

The dynamic pipe fixture exercised actual reads/writes, aliases and flags,
CLOEXEC, a nested child retaining an extra read alias after fd0 closed, an
extra write alias after fd1 closed, EOF while the child remained alive,
unrouted-pipe rejection without parent mutation, and EPIPE. The
[packaged static SDK test](../p0_sdk_pipe_closure_20261128/README.md) separately
qualified the delivered support archive without a diagnostic override.

The C++ and thread programs entered through both xsh and the newly built
static dash. They exercised shared GNU libstdc++/libgcc/libm, a separate C++
DSO, cross-DSO exceptions/RTTI/unwinding, TLS destructors, atexit, and
std::thread creation/join inside both the main constructor and application.
The outer static dash is separately bound and is not presented as a build of
the tested shared libc.

The GNU runtime used ordinary `make lib`, with 75 successful recorded steps;
shared GCC and all four program generations were newly built against that
composition. The public native identity includes the independent C SDK
manifest and capsule ABI. Producer receipts retain their build-only status.
`qualification.json` records exact source, native/C SDK, runtime, launcher,
program/root and dash identities, actual results and the replay command.
`source_bindings.json` records 399 source files individually checked against
[public source `0056c9fa`](https://github.com/Xiao-John/XylophoneOS/commit/0056c9fad097dddfeede319ff7c63b3ebd2bfcd5).
The GNU producer's original local revision `1b8b0ae` has the identical
complete tree `3c67a6f4ce7ee0061af3ef743c07b9d6757f1fb1`. Later report-only commits do not change
any listed source input; original raw identities are retained.

The public summary contains necessary source/artifact identities and results
without host inventories or serial transcripts. Raw local receipt digests
identify its origin and the flat root manifest binds the report leaves.
Replay requires the named immutable inputs inside the verified Preview 2
environment; caller-selected `XOS_*` paths denote their locations.

This qualifies the bounded public startup profile. Online DSO loading,
persistent/global policy, cross-descendant revocation, dynamic fork-to-exec
controller migration, terminal-actor dynamic exec, installed DHCP/dynamic-GNU
composition and physical hardware remain separate capabilities.
