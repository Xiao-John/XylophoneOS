# E08-5 Runtime handoff: normal exit and TLS destructors

This is an implementation handoff for the single-task-per-process C++ ABI path. It does not claim that target libstdc++/libsupc++ or E08-5 passed. The target C++ runtime is still incomplete; the parent agent owns the unified build and guest execution.

## Findings

The existing x86_64-elf GCC 16.2.0 emits a direct `__cxa_thread_atexit` call for a non-trivial `thread_local` destructor when compiled with `-fuse-cxa-atexit`. A real object was produced from `tests/fixtures/cpp_abi/tls_destructor_probe.cpp` with the installed cross G++ and the immutable v4 SDK snapshot. `nm -u` reported `_GLOBAL_OFFSET_TABLE_`, `__cxa_thread_atexit`, `__dso_handle`, and `puts`; the object also had `.tbss` and `.eh_frame`. This establishes the libc entry point XOS must supply. It does not establish that a target C++ runtime has been delivered.

GCC 16.2.0's `libstdc++-v3/libsupc++/atexit_thread.cc` supports the distinction: when configured for libc's `__cxa_thread_atexit`, it expects that symbol from libc; its fallback registers a single `atexit` callback and contains a FIXME that TLS cleanup should precede static and ordinary exit cleanup. XOS therefore implements the ABI entry directly and does not use the ordinary-atexit fallback. The object does not reference `__cxa_thread_atexit_impl`, so that spelling is not added speculatively.

The selected libc is newlib 4.6.0.20260123 (`x86_64-elf`; see [`docs/e06_libc.md`](../e06_libc.md) and [`docs/decisions.md`](../decisions.md)). The matching newlib `exit.c` sequence is `__call_exitprocs(status, NULL)`, `__stdio_exit_handler()` when present, then `_exit(status)`. `__call_exitprocs` removes a handler before invoking it and rescans when a handler adds another handler; this is the behavior needed for recursive registration during destruction. Newlib's `__cxa_finalize(dso)` routes through the same exit-procedure machinery with a DSO filter, so this XOS adapter does not separately replay C++ handlers or call `__cxa_finalize` a second time. References: [newlib 4.6.0.20260123 `exit.c`](https://sources.debian.org/src/newlib/4.6.0.20260123-2/newlib/libc/stdlib/exit.c) and [`__call_atexit.c`](https://sources.debian.org/src/newlib/4.6.0.20260123-2/newlib/libc/stdlib/__call_atexit.c). The newlib source archive itself is not present in this checkout, so the implementation is source-based and must still be link-checked against the actual delivered archive.

## Implementation

`src/user/libc/cpp_runtime.cpp` now exports the observed `__cxa_thread_atexit` symbol. It places each `(destructor, object)` pair on a private per-process LIFO list, allocated with newlib `malloc`; allocation failure and a null destructor return `-1`. The single-task model means this list belongs to the sole user thread in each process image; separate XOS processes have separate address spaces and lists. DSO is intentionally ignored because XOS currently has one static image and no dynamic unload.

The same file strongly defines `exit(int)`, so both explicit `exit()` and `main` returning through `main_entry.cpp` take the same path:

1. Drain the TLS destructor list LIFO, unlinking and freeing each node before invoking its callback. Destructors may register further TLS callbacks; the drain loop consumes those registrations in LIFO order.
2. Call newlib `__call_exitprocs(status, NULL)` for existing C++ global destructors and ordinary `atexit` callbacks.
3. If those handlers registered more TLS destructors, repeat the TLS drain and exit-handler pass until no TLS callback remains. Newlib itself rescans handlers registered by an exit callback.
4. Run newlib's stdio exit handler if non-null, then `_exit(status)`.

The adapter guards recursive `exit()` with an immediate `_exit(status)`. This prevents a destructor from recursively replaying TLS callbacks or newlib handlers. Recursive exit is an abnormal path; this guard deliberately does not claim that all remaining cleanup handlers run after a callback explicitly terminates the process. Normal exit and handler-added registrations are covered by the new guest probe. Existing init/fini handling and `__dso_handle` remain in place; `finish_cpp_runtime` remains an ordinary newlib callback registered before constructors, so global destructors and TLS destructors precede legacy dtors, reverse fini arrays, and frame deregistration.

The runtime object relies on newlib's existing `atexit`/`__cxa_atexit` implementation and does not redefine them. It also does not implement exception, RTTI, allocation, or guard ABI functions. `__stdio_exit_handler` is declared by the checked-in newlib `sys/reent.h`; `__call_exitprocs` is declared as the internal newlib C entry point because newlib does not install a public header declaration for it.

## New guest probe

`src/user/programs/tls_exit_probe.cpp` exercises both normal main return and an explicit `exit(0)` from `main`. Each run touches two non-trivial TLS objects in order A then B; B's destructor registers a late TLS callback. The required output order is B destructor, late TLS destructor, A destructor, ordinary `atexit` handler, global destructor, then fini-array callback. `tests/tls_exit_smoke.py` checks both routes, guest exit code, absence of `FAIL`, marker order, and return to the baseline task/page/completion counts. It requires the parent build to integrate the probe as `/bin/tls_exit_probe.elf` and include current source hashes in `build/manifest.json`.

## Static evidence and limits

The ABI fixture compile command was:

```text
/opt/homebrew/Cellar/x86_64-elf-gcc/16.2.0/bin/x86_64-elf-g++ -std=gnu++17 -ffreestanding -fno-exceptions -fno-rtti -ftls-model=local-exec -fuse-cxa-atexit -I .cache/xos_seed/gcc/stdcxx/prefix/include/c++/16.2.0 -I .cache/xos_seed/gcc/stdcxx/prefix/include/c++/16.2.0/x86_64-unknown-elf -I .cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490/include -c tests/fixtures/cpp_abi/tls_destructor_probe.cpp -o /tmp/xos_e085_tls_final/tls_destructor_probe.o
```

The runtime and new guest probe were independently compiled with these commands:

```text
/opt/homebrew/Cellar/x86_64-elf-gcc/16.2.0/bin/x86_64-elf-g++ -std=gnu++17 -ffreestanding -fno-exceptions -fno-rtti -fuse-cxa-atexit -Isrc/user/include -Isrc/shared/include -Isrc/third_party/newlib/x86_64-elf/include -I.cache/xos_seed/sdk_snapshots/1ba7c52c568725cac63c4a9e603aabd61f30e00db430ca0e5afb4fcfee956490/include -c src/user/libc/cpp_runtime.cpp -o /tmp/xos_e085_tls_final/cpp_runtime.o
/opt/homebrew/Cellar/x86_64-elf-gcc/16.2.0/bin/x86_64-elf-g++ -std=gnu++17 -ffreestanding -fno-exceptions -fno-rtti -ftls-model=local-exec -fuse-cxa-atexit -Isrc/third_party/newlib/x86_64-elf/include -c src/user/programs/tls_exit_probe.cpp -o /tmp/xos_e085_tls_final/tls_exit_probe.o
```

The compiler was GCC 16.2.0 targeting `x86_64-elf`, SHA-256 `b19620baa8aea69a02136bde577568987a5003f88c231fed16d09990a46c1eb9`. `x86_64-elf-nm` was GNU Binutils 2.47.20260726, SHA-256 `a7eebf858a985c75e1ca9ec669cf6b46b4ec5abb616b61e31c245d6ddf08286e`. The resulting object SHA-256 was `03838d571c82de7923001b375b06dfed65ae61b70996360a7780889a8e3e33b4`.

The modified runtime compiled as an independent object to `/tmp/xos_e085_tls_final/cpp_runtime.o` using the same cross compiler, `-std=gnu++17 -ffreestanding -fno-exceptions -fno-rtti -fuse-cxa-atexit`, and checked-in XOS/newlib headers. `nm` confirmed global definitions for `exit` and `__cxa_thread_atexit`, and undefined references to `__call_exitprocs`, `__stdio_exit_handler`, `_exit`, `atexit`, `malloc`, and `free`. Its SHA-256 was `064e722f7383b544621b4aa40267ff9b407c5a9b4390485cbd5cbba34248bf2b`; the source SHA-256 was `9b4fa1fb61bd22b231a18ec1aa195c0e5697ca8073fcef72685229f179b0c328`. The guest probe compiled independently to `/tmp/xos_e085_tls_final/tls_exit_probe.o`; object SHA-256 `6687c75f385efa0c86d3be4397957503b4924687e61c731076fdacaa1eb40723`, source SHA-256 `36c5775a1c23952a84396d87d5b6c5245b42d082d1239d58d3fe39be09c34f71`. The smoke script SHA-256 is `286deb047aa4877eb093bb9392e96a0688861ddac3dc0dddcbb1b00ace2fc203`. It passed Python AST syntax parsing; it was not run in QEMU.

No system build, full target link, or QEMU run was performed by this agent. The parent must integrate the two probe files in `scripts/user_build.py`, produce the SDK v5/runtime link, and run only `tests/tls_exit_smoke.py`. In particular, the strong `exit` interposition and availability of `__call_exitprocs` must be confirmed against the actual newlib archive during that link. Target exception, RTTI, containers, and complete libstdc++ support remain unverified.

New XOS-authored code in this change is Apache-2.0. GCC/newlib source is not copied into XOS; their source licenses and GCC runtime exception remain governed by their upstream notices and existing component records.
