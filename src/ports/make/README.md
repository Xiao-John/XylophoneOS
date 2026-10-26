# sbase Make for XOS

This port selects the real Make implementation from sbase commit
`c546c3a5724c81cee9a11d816a38ccdf17472129`, rather than GNU Make. The pristine
five C files, `make.h`, and repository MIT LICENSE live under `upstream/`.
`source_lock.json` binds every original file. Preserve the root MIT license
with the adapted upstream sources; new `posix_xos.cpp` and build tooling use
Apache-2.0.

`patches/0001_xos_always_build.patch` selects explicit `-B`, serial execution,
explicit prerequisites, and the original macro/recipe parser. It removes
timestamp-based inference, touch, and unimplemented signal calls. A target
graph records visiting/completed nodes, detects cycles, and runs shared
prerequisites once per Make process. `posix_xos.cpp` supplies a real
`fork`/`execve`/`waitpid` recipe path and authenticated foreground cancellation.
It never implements exec by spawning another program and waiting for it.

Build explicitly with `python3 scripts/build_make.py --sdk build/sdk` after
preparing `build/target_tools/as` and `ld`. This builds only the four adapted
engine sources and the XOS backend; upstream `posix.c` is retained as source
material and is not compiled. Output is isolated beneath
`.cache/xos_seed/make/<fingerprint>/`, with tool, source, SDK, license and ELF
digests. The manifest says `built_not_run`; neither build success nor this
README is a guest acceptance result.

The selected behavior, exclusions, and required guest evidence are documented
in `docs/make_subset.md`. This port does not install itself, change a work disk,
or add a `/bin/sh` alias.

The ordinary SDK supplies C headers; the C++ backend intentionally uses their
global C declarations rather than unavailable hosted <c...> wrappers. Status
137 propagated by the recipe Shell is reserved for forced termination, so it
cannot be ignored by -i or '-' even when a script explicitly returns 137.
Guest self-build uses the documented short-option native configuration and
current SDK at /xos_sdk, preserving the released compiler's original /sysroot.
Build manifests remain built_not_run; separate qualification reports bind
actual guest execution and artifacts.
