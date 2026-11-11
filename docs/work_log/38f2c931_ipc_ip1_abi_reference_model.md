# 38f2c931 IPC IP1 ABI registration and reference model

## Scope and result

Completed IP1 from `docs/plans/ipc_sel4.md` on branch `codex/ipc-ip1`, based on
the synchronized `main` commit `2b2816b`. Registered syscall 88 and froze its
version 1 request layouts, actions, limits, features, errors, rights, deadline,
and lifecycle semantics. The kernel recognizes only `query_features`; it
reports known mask `0x1f`, supported mask `0`, and the registered limits.
Every endpoint action still returns `unsupported`. Both SDK profiles advertise
`registered_unsupported` with an empty feature list. This does not implement or
qualify IPC endpoint behavior.

Added an executable host-only reference state machine for handle ownership and
delegation, bounded queues, payload snapshots, FIFO delivery, reply-token
lifecycle, deadlines, close, and `reply_receive` partial success. It is a
contract oracle, not a product backend. Updated the IPC plan, ABI registry,
contract, SDK notes, and this work log index. `docs/state.md` was left untouched
as required by `docs/Discipline.md`.

## Files

- `src/shared/include/xos/ipc_v1_abi.hpp`: syscall/action/error/feature enums,
  fixed wire structures, sizes, and offsets.
- `src/kernel/arch/x86_64/tasks.cpp`: validated feature-query gate; all endpoint
  operations remain unsupported.
- `src/user/include/xos/ipc_v1.hpp`: query-only SDK wrapper and feature check.
- `scripts/ipc_v1_manifest.py`, `scripts/user_build.py`,
  `scripts/build_threading_sdk.py`: shared unsupported manifest entry in both
  SDK builders.
- `tests/ipc_v1_reference_model.py`: 18 host model tests.
- `docs/contracts/abi_registry.md`, `docs/contracts/ipc_v1.md`,
  `docs/e04_loader_sdk.md`, `docs/plans/ipc_sel4.md`, and the linked historical
  work log: registration, contract and status updates.
- `docs/work_log/README.md`: index entry.

## Decisions

Syscall 88 is a versioned action multiplexer. Its first runtime behavior is a
capability query with no supported features, so callers can distinguish a
registered ABI from an implemented backend. Normal and experimental threaded
SDK manifests share one helper to prevent support claims from drifting. The
endpoint-create rights field requests a nonzero subset of known rights; this is
reflected in the contract and model. No kernel endpoint data structures or
user-visible endpoint stubs were added in IP1.

## Checks and evidence

Environment: Debian GCC 14.2.0, Python 3. The commands below were run from the
repository root:

- `python3 tests/ipc_v1_reference_model.py` — PASS, 18 tests.
- `python3 -m py_compile scripts/user_build.py scripts/build_threading_sdk.py scripts/ipc_v1_manifest.py tests/ipc_v1_reference_model.py` — PASS.
- `python3 tests/docs_consistency.py` — PASS, 859 local links, 76 allocated
  syscalls, and 73 history sources.
- `python3 tests/report_manifest_check.py` — PASS; compliant and grandfathered
  report inventories as expected, no failures.
- `g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -Isrc/shared/include -fsyntax-only build/ipc_ip1_syntax/abi_size.cpp` — PASS; shared ABI header/layout.
- `g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -ffreestanding -fno-exceptions -fno-rtti -nostdinc++ -Isrc/shared/include -Isrc/user/include -fsyntax-only build/ipc_ip1_syntax/sdk_syntax.cpp` — PASS; SDK wrapper.
- `g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -ffreestanding -fno-exceptions -fno-rtti -nostdinc++ -Isrc/shared/include -Isrc/kernel/include -Isrc/kernel -Ibuild/ipc_ip1_syntax/generated -fsyntax-only src/kernel/arch/x86_64/tasks.cpp` — PASS; kernel translation unit syntax with the available generated-header stubs.
- `git diff --check` — PASS before final staging.
- `python3 tests/check_public_evidence_paths.py --index --base origin/main` —
  PASS (`PUBLIC_READY`, no findings); this first scan saw only the then-staged
  index. It must be rerun after staging the complete final diff.
- `make license-audit` — NOT RUN to completion; its prerequisite build stopped
  because NASM is not installed (`NASM not found`). The attempted standalone
  `tests/license_audit.py` path does not exist; the repository's target is the
  Makefile target above.

Not run: full XOS build, boot/guest qualification, syscall runtime tests, and
hardware/VM endpoint behavior. The kernel check above is syntax-only and uses
temporary generated-header stubs; it is not a product build. The current query
gate and host model do not satisfy IP2 or claim IPC support.

## Handoff

After this PR is merged, begin IP2: implement authenticated endpoint handles,
quotas, synchronous call/receive/reply, deadline and cancellation/close
semantics, then qualify them in a real guest before advertising any feature.
Keep the query and both SDK manifests at zero supported features until that
qualification is complete.
