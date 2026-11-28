# Final integrated native lifecycle and standard-stream qualification

The final integrated source passed **48 lifecycle/controller suite invocations**
and **45 static standard-stream compatibility checks** in four sequential real
guest sessions. Every invocation or complete compatibility round restored the
new system's exact baseline of **129778 free pages / 2 tasks / 0 completions**.
All observed program exits were normal and successful.

## Fixed composition

All production, fixture, builder and runner source is fixed at
`299ea47cc991fb781e8671c41213a02c169f4130`, with **no per-file overlays**. The
complete execution export's 8,837 Git files were checked against immutable Git
bytes before execution and checked again afterwards. All 2,207 source files in
the native system manifest match that same revision. Forty-three explicit
fixture, runner and helper inputs are additionally listed in `source_binding.json`.

The actual native build is `faad61f4f20be0f7`. Its boot ISO is
`c200100651fe8161e69773c0963ebf3bb1c0dcb899f1b07b3aa66ddb10c19dae`, and the SDK
manifest is
`fc8b81adef3b0397bb7743093091ffc21d07f14c6a33504e1d087d11e8601ffa`.
The SDK file-inventory tree digest is
`25c705d9e1388330db72d75ca1c22e129fe7a330a7810c9afedd49fdd5ebdde6`.
The separate SDK receipt algorithm also includes directory entries and yields
`dca0aa4e45262357ba3a1dfe10b33b65287942b6a086183868db88febfa68f93`;
these are different inventory algorithms applied to the same complete SDK.

All four fixtures were freshly compiled using that SDK in Preview 2. The static
compatibility fixture explicitly compiles the same unmodified production
`load.cpp` from the final revision; all other archives, headers, CRT and kernel
inputs are the bound final native composition.

| Suite | Executed coverage | Result |
|---|---|---|
| Launch controller | 11 cases × 3 rounds | 33/33 passed |
| IPC lifetime, authority and quota | 4 modes × 3 rounds | 12/12 passed |
| IPC absolute deadlines | 6 conditions in each of 3 runs | 3/3 suite runs passed |
| Ordinary static standard streams | 15 checks × 3 rounds, including 12 actual child executions | 45/45 passed |

The actual fixture ELFs are:

| Fixture | SHA-256 |
|---|---|
| Launch controller | `697fbd7288519fc2442bb3a8335e8d31e11ce0859a21cd3e24a1a4d5b7a79ff1` |
| IPC lifecycle | `84f1794384370e08c14df31bd03fd2080a91500a047823e1487ef44bce679525` |
| IPC deadline | `e99a36f928611d0b0bff18d4e04355f2ba496bfff2843b072fa45dad6d119e24` |
| Static stdio probe | `19c92eccf996154f2f9f5720985fb68c070753fbae3e1f92c35ebbf59c8001cc` |

## Behavior verified

The controller runs success, cancel, entry failure, entry revocation, prepare
revocation, timeout, early exit, malformed messages, multiple children, stale
ALLOW and stale CANCEL. This includes authenticated READY/ACK, public wait
pumping, real same-PID replacement, current-policy admission, finite deadlines
and recovery from expired queued messages.

The IPC modes retain their required event loops and resource assertions. They
exercise actual blocked receivers and senders across revoke, close, process
exit, fault and cancellation; failed-exec authority preservation; successful
exec revocation; restart authentication and stale-handle rejection; per-owner
quota and peer isolation. The deadline suite checks receive timeout, send
timeout without payload loss, expired readiness-first behavior, rejected scope
or legacy forms, readiness wakeups, and close wakeups with full-width finite
deadline behavior.

The standard-stream suite executes actual raw and v3-marked ELFs. It verifies
startup v2 compatibility for representable ordinary streams, retained v3
startup for opted-in targets, closed stdin, pipe input `DATA` and aliased output
`OUTERR`. Extra FDs, unsupported flags, inconsistent routes or aliases, Files
streams, cleanup records, replacement exec, malformed markers and the pinned
bootstrap path all retain their strict inspect-stage rejection. After shutdown,
offline FAT readback confirms that the rejected Files target retained its data.

Each suite uses real native IPC, Files, process and pipe operations. The final
resource baseline is measured afresh. The earlier `c1575e2adfc6fa5d` evidence
remains historical and its page count or source identity is not substituted here.

## Replay and exported records

Use a complete source export at the stated revision and the exact final native
build. Build the fixtures with `build_launch_control_probe.py`,
`build_ipc_exec_probe.py`, `build_ipc_deadline_probe.py`, and
`build_static_stdio_probe.py`, each in a new output directory. The first three
take `--sdk "${XOS_FINAL_NATIVE_SOURCE}/build/sdk"`; the stdio builder takes the
system and immutable source explicitly.

Run `tests/launch_control_guest.py --repeat 3`; run
`tests/ipc_exec_guest.py --repeat 3 --serial-only --suite lifecycle`, then the
same runner with `--suite deadline` and its corresponding fixture; finally run
`tests/static_stdio_compat_guest.py --repeat 3` with the final system and source.
Pass each runner its actual fixture and a new output directory. Run guests
sequentially; the four receipts record the exact QEMU commands and inputs.

Each build receipt retains its actual build-only status. Execution observations
are in the separate guest reports and full serial transcripts; the stdio rounds
are also exported individually. The complete native source/artifact manifest
is retained. `conversion.json` records unpublished original byte identities and
mechanical path/transcript transformations. Only the flat root `manifest.json`
hashes exported leaves.

This closes the final-source native lifecycle and strict static-stdio regression
gates for these exact bytes. The SDK rollback, installer, public GNU C/C++ and
dynamic generation gates require their own final compositions and observations.
Explicit-channel inheritance stress, terminal/display/Interactium combinations,
durable cross-descendant revocation and process-tree budgets are outside these
suites; their omission is retained in the original runner reports.
