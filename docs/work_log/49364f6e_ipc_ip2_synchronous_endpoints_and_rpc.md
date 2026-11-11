# 49364f6e IPC IP2 synchronous endpoints and RPC

## Scope and current result

Started IP2 on `codex/ipc-ip2`, based on synchronized `main` at `22acb8a` (IP1
PR #107 and the subsequent P4A commit are included). Added the x86-64 single-CPU
sys88 slow path for endpoint creation/delegation/close, authenticated
process-bound handles, quotas, queued and delivered calls, receive badge,
one-shot reply tokens, `reply_receive`, deadlines, close, process exit and
successful exec revocation. Blocked user buffers are pinned across the wait and
copied out when the owning thread resumes. Added SDK wrappers. The call ABI now
uses its former reserved word at offset 72 for `reply_label_out` while retaining
its 88-byte size; this fixes the mismatch between reply labels in the logical
contract and the registered wire structure before any feature is enabled.

This is **not yet an IP2 completion**. The kernel feature query remains at
supported mask zero and both SDK manifests remain `registered_unsupported`.
The required real guest qualification did not run because the environment lacks
the pinned target build tools. No IPC capability is claimed as supported.

## Files changed

- `src/kernel/arch/x86_64/tasks.cpp`: IPC v1 object tables, syscall operations,
  blocking wait completion, deadline arbitration, VM range pins and lifecycle
  revocation.
- `src/kernel/core/thread_lifecycle.hpp`: IPC v1 call/receive wait kinds.
- `src/shared/include/xos/ipc_v1_abi.hpp`: reply label output in the existing
  call wire slot, with size and offset assertions.
- `src/user/include/xos/ipc_v1.hpp`: syscall wrapper for endpoint, call,
  receive, reply and reply-receive operations.
- `docs/contracts/abi_registry.md`, `docs/contracts/ipc_v1.md`,
  `docs/e04_loader_sdk.md`, `docs/plans/ipc_sel4.md`: implementation status,
  reply-label layout clarification and unsupported qualification boundary.
- `docs/work_log/README.md` and this record.

## Verification

Environment: Debian GCC 14.2.0 and Python 3. Kernel translation unit syntax and
object generation used temporary generated-header fixtures in ignored `build/`
paths; this host compiler is not the locked target cross toolchain.

- `g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -ffreestanding -fno-exceptions -fno-rtti -nostdinc++ -Isrc/shared/include -Isrc/kernel/include -Isrc/kernel -Ibuild/ipc_ip1_syntax/generated -fsyntax-only src/kernel/arch/x86_64/tasks.cpp` — PASS.
- Strict x86-64 freestanding `g++ -c` for `tasks.cpp` — PASS; object generated
  under `build/ipc_ip2/tasks_host_gcc14.o`.
- Strict freestanding SDK wrapper syntax check — PASS.
- `python3 tests/ipc_v1_reference_model.py` — PASS, 18 pre-existing host model
  cases. These test the contract model, not the new kernel path.
- `python3 tests/docs_consistency.py` — PASS, 866 local links, 76 allocated
  syscalls and 73 history sources.
- `python3 tests/abi_doc_consistency.py` — PASS.
- `python3 tests/report_manifest_check.py` — PASS.
- `git diff --check` — PASS at last check.
- `python3 scripts/build.py --output-dir build/ipc_ip2/system` — NOT RUN beyond
  preflight: stopped with `NASM not found`.
- `python3 scripts/license_audit.py` — NOT RUN to completion because the build
  prerequisite has not created `build/sdk/manifest.json`.
- QEMU guest IPC tests, full target build, resource-leak/repetition tests,
  fork/exec guest tests, and public-index scan of the final staged diff — NOT
  RUN.

## Handoff and exit conditions

Before changing `ipc_v1_feature_ip2_mask`, `scripts/ipc_v1_manifest.py`, or
either SDK manifest from unsupported, install/use the repository-pinned GCC
16.2.0 x86_64-elf toolchain, Binutils 2.47, NASM 3.02 and QEMU 11.1.2, then
build and run a real guest test. The guest suite must cover create/delegate
rights and badge, successful call/reply labels, receive-first and queued paths,
buffer-too-small retry, deadlines before/after delivery, reply-once,
reply_receive partial success, close/exit/fault/successful-exec revocation,
quotas and repeated resource recovery. Review/fix any behavior failure before
claiming IP2 complete. Keep the feature mask and both manifests unsupported
until all applicable checks pass.
