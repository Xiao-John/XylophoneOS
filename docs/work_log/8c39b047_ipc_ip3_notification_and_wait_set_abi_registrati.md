# 8c39b047 IPC IP3 notification and wait-set ABI registration

## Scope and result

Continued IPC on `codex/ipc-ip3`, based on `origin/main` at `9c51eb4` after
IP2 PR #109 merged. This increment
registers notification and wait-set actions 8–18, fixed request/event layouts
and limits, and SDK thin wrappers. The x86-64 slow path now implements
notification create/delegate/signal/wait/close, OR-merged badge bits, deadline
waits, close wakeup and process/exec revocation. It also implements wait-set
create/delegate, endpoint/notification sources, add/remove/wait/close, level
endpoint readiness, notification consumption, buffer-too-small without
consumption, persistent closed events, deadlines, readiness wakeups and
lifecycle cleanup. Runtime feature query remains zero, and both SDK manifests
remain `registered_unsupported`. This is not guest acceptance.

The first wait-set source set is explicitly limited to IPC v1 endpoint readiness
and notifications. IRQ, process-exit and legacy channel wait-many are excluded.
Notification badges are OR-merged bit masks; wait consumes accumulated bits.
Closed sources remain observable until removed. Readiness checks and blocking
registration run within the single-CPU syscall gate; blocked outputs are pinned.

## Files changed

- `src/shared/include/xos/ipc_v1_abi.hpp`: action numbers 8–18, rights, limits,
  event kinds and fixed layouts with size assertions.
- `src/user/include/xos/ipc_v1.hpp`: wrappers for notification and wait-set calls.
- `tests/fixtures/ipc_v1/ipc_v1_probe.cpp`, `tests/ipc_v1_guest.py`: reusable
  guest coverage for concurrent RPC, deadline/reply race, close wakeups,
  endpoint handle quota recovery, notification merge/blocking, wait-set
  notification and endpoint readiness, capacity retry, and resource baseline
  checks.
- `src/kernel/arch/x86_64/tasks.cpp`, `src/kernel/core/thread_lifecycle.hpp`:
  notification and wait-set object/handle tables, authorization, blocked waits,
  deadlines, event collection and lifecycle paths.
- `docs/contracts/ipc_v1.md`: ABI semantics and explicit unsupported boundary.
- `docs/contracts/abi_registry.md`, `docs/e04_loader_sdk.md`,
  `docs/plans/ipc_sel4.md`: registration and next implementation step.
- `docs/work_log/README.md` and this record.

## Checks

Environment: host GCC 14.2.0. Shared ABI header and SDK wrapper strict syntax checks:

```text
printf '#include <xos/ipc_v1_abi.hpp>\nint main() {}\n' | g++ -std=c++20 -ffreestanding -fsyntax-only -Isrc/shared/include -x c++ -
PASS
printf '#include <xos/ipc_v1.hpp>\nint main() {}\n' | g++ -std=c++20 -Wall -Wextra -Werror -Wconversion -Wshadow -ffreestanding -fno-exceptions -fno-rtti -nostdinc++ -Isrc/shared/include -Isrc/user/include -x c++ -fsyntax-only -
PASS
```

Strict freestanding syntax checks for the kernel translation unit and SDK
header passed. `tests/docs_consistency.py`, `tests/abi_doc_consistency.py`,
`tests/check_public_evidence_paths.py --index --base origin/main`, and
`git diff --check` passed. These are source/documentation checks, not runtime
behavior evidence. The guest probe source and harness pass host syntax checks;
the guest script itself was not run. The user owns guest acceptance.

Run the guest qualification harness after building the matching threading SDK
and system image:

```text
python3 tests/ipc_v1_guest.py --system build/ipc_ip3/system \
  --sdk build/threading_sdk --output build/ipc_v1_guest_run
```

## Next step

Owner: guest-qualify notifications and wait sets, focusing on signal merge and
zero badge, wait/signal ordering, rights/delegation, event capacity without
consumption, endpoint readiness, source close/revocation, deadlines, process
exit/exec and repeated quota recovery. Keep feature query and manifests
unsupported until that acceptance.
