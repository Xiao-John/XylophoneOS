# dash for XOS

Optional `/usr/bin/dash`, launched by Xshell. No default-shell replacement or
`/bin/sh` alias. See `docs/implementation/shell.md` for accepted scope and guest evidence.

`source_lock.json` pins the pristine release archive. `patches/` changes the
upstream sources; `jobs_xos.c` and `signals_xos.c` replace the selected upstream
backends, `admission_xos.c` is appended to eval.c, and `console_xos.cpp` implements
canonical serial input using the existing SDK, including UTF-8 validation and
code-point-aware backspace. The signal hooks are private
shell bookkeeping, not successful libc signal emulation. Unsupported operations
fail explicitly. C2 adds bounded single-thread eager-copy fork; vfork remains unavailable.

The accepted B0/B1 profile recursively admits `case`, shell functions, dot
scripts, and the existing parameter expansion. It rejects pipelines,
subshells, background execution, and command substitution. For a
bare `dash` launched by Xsh, the process ABI supplies a bounded depth-two
construction capability; this user-space backend delegates one remaining level
only to the fixed GCC/G++ driver basenames. The kernel never matches tool names.
The legacy `exec-driver dash` path remains depth one and cannot compile through
GCC. See `docs/plans/dash.md` for the exact boundary.

B2 admits ordered `<`, `>`, `>>`, `2>`, and descriptor duplication/closure for
descriptors 0-2. Dash applies and restores builtin redirections with its normal
redirection stack; external commands receive file-service references to the
same open description, rather than reopening a pathname. Pipelines, subshells,
background jobs, command substitution, and here-documents remain unavailable.

Run `make dash` (or `python3 scripts/build_dash.py --sdk build/sdk`) explicitly.
The source tarball is vendored at `upstream/dash-0.5.13.5.tar.gz`; `make disk`
builds dash and preinstalls `/usr/bin/dash` into a newly created work disk.
Existing disks are left alone; use `scripts/install_dash.py` to add it manually.
The output manifest binds all port and SDK inputs; it says built_not_run until
separate guest evidence is considered. No installation into a user's disk occurs.

Preserve the complete `upstream/COPYING` and original per-file notices. The
upstream mksignames generator and its output are omitted in this no-signals
profile. New local backend/build/test files are Apache-2.0; modified upstream
files retain their original licenses. The pinned upstream tarball is kept under
`upstream/` so an offline checkout can build and preinstall dash.


C1 experimental branch adds external-only, foreground pipelines of at most four
simple-command stages. All stages launch before any blocking wait. Parent pipe
ends close promptly, ordered stage redirections override pipe defaults, failed
launches cancel/collect already started children, and Escape cancels the whole
foreground pipeline even during construction. The last stage supplies status;
missing commands are 127, other spawn failures 126, cancellation 137. A fifth
stage is rejected before execution. Fewer free process slots can fail a shorter
pipeline; the global eight-process quota is unchanged.

This intermediate C1 evaluator expands external arguments in the parent shell.
Full subshell isolation, including side effects of arithmetic expansion, belongs
to C2 and is not claimed here. Builtins/functions in pipelines, subshells, command
substitution, here-documents, background jobs and real exec remain rejected.
Actual evidence and remaining regressions are recorded in work log 0047.


C2 uses eager-copy fork, preserving the actual Shell heap/AST/functions, variable
flags, positional parameters, cwd, all libc descriptors and file-service opens.
The copied continuation cannot run before an authenticated file-session clone
ACK. Multithread profiles reject fork; depth is bounded to three and physical
memory exhaustion rolls back the partially copied image. Literal external
stages keep C1's direct launch; stages with expansion, builtins, functions or
compound commands fork before evaluation. This keeps argument side effects out
of the parent. pipefail and tested errexit contexts use real collected status.

Command substitution supports both $(...) and backticks through the upstream
expander, with a declared 1 MiB raw stdout bound and tail-newline stripping.
Errors cancel/reap the capture child and close its read descriptor, so an
interactive Shell can continue. This is not asynchronous signal delivery or
real exec replacement; those remain C3 work. Detailed evidence is in 0048.


C3 uses read-only sealed anonymous file descriptions for here-documents, keeping
large bodies out of pipe prefill and deleting storage at last close. Explicit
exec preserves PID/TID and restores complete descriptor groups through startup
v3, including per-FD CLOEXEC. A read-only .xos.exec CRT declaration is required;
legacy static tools remain on ordinary spawn, with explicit exec rejected.
The current SDK's runtime libraries, CRT and linker must be used together.
The unstripped Dash ELF is retained for debugging; the installed runtime ELF
removes debug sections only and the builder verifies unchanged entry, PT_LOAD
and PT_TLS contents. The existing one-MiB ISO payload budget is unchanged.
Optional sbase Make has a separate explicit -B, serial profile; see 0049 and
make_subset.md for exact limitations and real guest evidence. This still does
not provide POSIX asynchronous signals, background jobs, or thread-profile
fork/exec. No /bin/sh alias or formal Release is installed by the builders.
