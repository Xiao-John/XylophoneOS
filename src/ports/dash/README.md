# dash for XOS

Optional `/usr/bin/dash`, launched by Xshell. No default-shell replacement or
`/bin/sh` alias. See `docs/shell_subset.md` for accepted scope and guest evidence.

`source_lock.json` pins the pristine release archive. `patches/` changes the
upstream sources; `jobs_xos.c` and `signals_xos.c` replace the selected upstream
backends, `admission_xos.c` is appended to eval.c, and `console_xos.cpp` implements
canonical serial input using the existing SDK, including UTF-8 validation and
code-point-aware backspace. The signal hooks are private
shell bookkeeping, not successful libc signal emulation. Unsupported operations
fail explicitly. No fork or vfork implementation is introduced.

The accepted B0/B1 profile recursively admits `case`, shell functions, dot
scripts, and the existing parameter expansion. It still rejects redirection,
pipelines, subshells, background execution, and command substitution. For a
bare `dash` launched by Xsh, the process ABI supplies a bounded depth-two
construction capability; this user-space backend delegates one remaining level
only to the fixed GCC/G++ driver basenames. The kernel never matches tool names.
The legacy `exec-driver dash` path remains depth one and cannot compile through
GCC. See `docs/dash_port_plan.md` for the exact boundary.

Run `python3 scripts/build_dash.py --sdk build/sdk --archive PATH` explicitly;
the frozen 0.0.1-1024 release SDK predates the B0 `xos_posix_spawn_driver` symbol.
Python 3.12 or newer is required for the tar extraction filter.
The output manifest binds all port and SDK inputs; it says built_not_run until
separate guest evidence is considered. No installation into a user's disk occurs.

Preserve the complete `upstream/COPYING` and original per-file notices. The
upstream mksignames generator and its output are omitted in this no-signals
profile. New local backend/build/test files are Apache-2.0; modified upstream
files retain their original licenses. No upstream archive is committed here.
