# d923f231 IPC IP5 short-message fastpath and guest latency probe

## Scope and result

IP5 builds on `origin/main` (which contains the PR #111 merge). It adds a constrained
direct switch for a caller whose short call was delivered to a ready receiver
blocked in `receive` or `reply_receive`. The scheduler still applies its liveness,
continuation-owner and ready-state checks, then falls back to its ordinary FIFO
picker. The fastpath is limited to non-poll calls with request length and reply
capacity at most 64 bytes; deadline, rights, FIFO delivery, reply-token and user
buffer pinning rules remain in the common IPC path.

Endpoint handle authorization now uses a 512-slot open-addressed index over the
existing bounded handle table. Inserts and removals update the index; lookup still
checks live record and holder PID. IPC payload snapshots use a word-at-a-time copy
with a byte tail at the same validation/pinning boundaries. Other kernel copies
are unchanged.

The PR also opens the four already guest-qualified IP2/IP3 feature bits in the
runtime query and both SDK manifests: `endpoint_call_v1`, `deadline_v1`,
`notification_v1`, and `wait_set_v1` (`supported_features=0x0f`). The evidence is
PR #111's same-build three-run guest acceptance with race/resource checks and an
unchanged resource baseline. `bulk_grant_v1` (`0x10`) remains unsupported until
IP4 acceptance.

## Files changed

- `src/kernel/arch/x86_64/tasks.cpp`: direct receiver preference, endpoint handle
  index, bounded payload copy; supported query mask.
- `src/shared/include/xos/ipc_v1_abi.hpp`: named IP3 and aggregate supported masks.
- `scripts/ipc_v1_manifest.py`: shared ordinary/threading SDK feature declaration.
- `tests/fixtures/ipc_v1_fastpath/ipc_v1_fastpath_probe.cpp` and
  `tests/ipc_v1_fastpath_guest.py`: reusable latency/semantic/resource probe.
- `tests/ipc_v1_reference_model.py`: supported feature and manifest expectations.
- `docs/contracts/ipc_v1.md`, `docs/contracts/abi_registry.md`,
  `docs/e04_loader_sdk.md`, `docs/plans/ipc_sel4.md`, and this work log.

## Probe and limitations

Run after building a system image and threading SDK from the same source and
toolchain:

```text
python3 tests/ipc_v1_fastpath_guest.py \
  --system build/ipc_ip5/system --sdk build/threading_sdk \
  --output build/ipc_v1_fastpath_run
```

The probe records p50/p95/p99 round-trip nanoseconds for 0, 8, 64, 128 and
256-byte messages, with a blocked-receiver server and a polling-fallback server,
120 measured samples each after a warmup. The kernel direct-switch predicate
should be eligible only for 0/8/64-byte cases (reply capacity equals payload
length). It verifies returned label/data, query mask, endpoint close and thread
join. The polling fallback is a different server strategy; it does not force an
otherwise identical kernel call through a runtime-selectable slowpath. QEMU
measurements are comparative and are not hardware latency claims.

## Checks and next step

- Kernel translation-unit strict host syntax check — PASS (using the existing
  generated-header stubs; this is not target code generation or a full build).
- Guest fixture strict host syntax check — PASS.
- Python `py_compile` for the IPC manifest, guest runner and reference-model test — PASS.
- `tests/docs_consistency.py`, `tests/abi_doc_consistency.py`, and
  `git diff --check` — PASS.
- `tests/check_public_evidence_paths.py --index --base origin/main` —
  `PUBLIC_READY` (13 changed paths, no findings).
- Full target build, host reference-model suite and guest/QEMU runs — NOT RUN.
  Guest acceptance belongs to the owner; no performance values are claimed by
  this implementation PR.

Next: build the system and threading SDK from this exact source/toolchain, then
run the command above. Keep the four qualified IP2/IP3 bits enabled and bulk
grant disabled. Claim IP5 performance only from the resulting report, with QEMU
results described as comparative rather than hardware latency.
