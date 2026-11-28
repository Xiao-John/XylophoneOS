# Static C++ SDK builder recovery

Scope: P0-R1's reusable static C++ runtime recipe. The previous unpublished
worktree was lost; this implementation and its qualification were reconstructed
using the verified Preview 2 Linux SDK. Source checkpoint: `c9c4dada`.

`scripts/build_glibc_static_cxx.py` authenticates pinned GCC 16.2.0, requires a
separate authenticated glibc C SDK, configures the native POSIX/generic-locale
C++ runtime, and replaces exactly the five qualified unwinder members. It
rechecks input SDK identity, all recipe inputs and tools; the exported SDK
carries the complete recipe, signer materials and licenses. Output directories
must be new and independent of the C SDK.

Fresh validation completed on 2026-11-28: all 14 build steps passed, detached
C/C++ consumer build/check/pack passed, and 15 packaged recipe inputs matched
in a receiver with no repository mount. The receiver loaded the standalone
builder CLI; a second complete GCC rebuild in that receiver was not run.
Eleven real-system executions passed with Xsh, dash, cwd/access, C++
constructors/threads/TLS/unwinding/stack bounds, stock xypm and FAT readback.
Every execution restored `free=129796, tasks=2, completions=0`.

System build `5808397c580ec49c`; SDK tree
`32b7bec6fc9e85ce2997cd3659fac0c2ecbf05ba7a84a099d9efbb637f760548`.
Compiler: GCC 16.2.0; binutils 2.47.20260726; QEMU 11.1.3. Commands, source
authentication, byte identities, serial output and portable conversion rules
are in [the flat qualification report](../reports/glibc_static_cxx_recovery_20261128/README.md).

This module closes the recoverable C++ recipe and focused static-runtime
qualification. Its system is the existing newlib profile. The final integrated
glibc default SDK, release/installer/package composition, detached relinks,
v6 material freeze and genuine frozen-newlib cold-boot rollback remain P0-R1
and must use fresh final-source artifacts. No release asset or tag was published.
