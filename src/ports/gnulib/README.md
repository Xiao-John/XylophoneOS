# GNU/gnulib on the XOS glibc profile

Issue #133 originated with GNU gzip 1.14 on the former newlib target. New GNU
ports use the explicit `x86_64-unknown-xos` glibc SDK. They do not masquerade as
Linux, mix libc headers, or add another per-port copy of newlib compatibility
types. Gnulib's existing glibc branch supplies program-name handling and its
generated headers supply portable `O_BINARY`/`S_IRWXUGO` definitions. The actual
XOS libc supplies `lstat`, `fdopendir`, wide types, and finite FD limit queries.

`scripts/gnulib_xos.py` is the common build-environment entry point. It sanitizes
inherited Autoconf/gnulib answers, uses the selected SDK's compiler/header/link
inputs, and generates a configuration site from the SDK's actual stub list.
The public `sigaction` name is disabled when the backend `libc_sigaction` is a
stub. The no-signal profile also disables `sigprocmask`, whose glibc stub has no
link warning because `abort` references it. Merely linking a symbol is not
evidence that the syscall is implemented.
No blanket positive `gl_cv_*` answers are injected. Package-specific omissions
must remain explicit and must be covered by the port's consumer tests.

`no_signal_xos.patch` fixes gnulib's assumption that absent signal functions
imply absent signal types and a usable Windows-style `signal()` fallback. XOS
keeps glibc's real types and set-manipulation routines; delivery/mask operations
return `ENOTSUP` without modifying output. The consumer checks these failures
and byte-for-byte preservation of the output structures. This is an explicit
unsupported backend, not a simulated signal subsystem.

`config_sub_xos.patch` adds the real XOS spelling to the GNU config.sub snapshot
carried by gzip 1.14. The controlled patch must apply successfully and config.sub
must return the expected canonical target. Another package with a different
config.sub snapshot needs a reviewed recognition patch, not a guessed host.

The libc FD table has 32 entries shared by file, pipe, terminal, console and
socket routes. `getrlimit(RLIMIT_NOFILE)` and `getdtablesize()` report that actual
capacity from the same private constant used to allocate the table. Other
resource limits and `setrlimit` remain unsupported; this does not advertise
resource enforcement that the backend does not have. The files service's
separate open-description quota can make independent opens fail sooner.

`tests/fixtures/gnulib/consumer.c` is compiled against a real configured gnulib
tree and its target archive. It checks program names, wide types/flags, stat,
directory ownership, actual descriptor exhaustion, error preservation and
resource queries in XOS. `tests/gnu_gzip_guest.py` adds the real gzip program,
data roundtrips, failure handling and both shell entry points.

This is a reusable XOS/glibc strategy, not an upstream gnulib submission or a
claim that coreutils, tar, sed, grep and findutils have all been ported. Their
additional modules, runtime behavior and distribution materials need their own
qualified ports. The frozen legacy newlib SDK is unchanged.
