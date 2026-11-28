# Launch-control recovery qualification — 2026-11-28

This is new evidence for the recovered source, based on the combined remote
modules at `f7240faae1fe1ef6f3dfae44fa21aef864849f23` and controller checkpoint
`3d7747f1`. The earlier execution filesystem and unpublished artifacts were
lost. No earlier pass result has been relabeled as this source's qualification.

## Observed result

- Production controller with the kernel trap boundary modeled: 15 independent
  cases, once ordinarily and once with AddressSanitizer/UndefinedBehaviorSanitizer,
  all 30 passed. A real host fork during the held admission lock also exercises
  the copied PID-lock recovery; this is explicitly a host model boundary test.
- Native guest: 11 scenarios repeated three times, all 33 passed. The fixture
  performs real kernel same-PID exec and checks the surviving PID, generation,
  ACK, actual wait completion, failure phase/root, and channel reclamation.
- Every guest execution returned exactly to `free=129781, tasks=2, completions=0`.
- Native fixture source and SDK exports were matched before linking. The runner
  verified all raw system manifest source/artifact hashes before and after the
  guest, plus the SDK tree hash and fixture receipt/artifact hashes.

The final system build is `cd41a13a9b8bfc61`. `system-binding.json` retains the
raw manifest's SHA-256, every source and artifact binding, tools and configuration;
only its repetitive build command arrays and layout symbol data are omitted.
The other JSON files retain the original report contents. Logs are plain text;
serial exports normalize line endings to LF and remove trailing whitespace.
`serial-bindings.json` records both raw and exported hashes and that transform.
`evidence_index.json` hashes every published leaf other than itself.

The first native attempt correctly rejected a fixture descriptor send to a
building, unstarted child. The final fixture sends immediately after spawn
returns and before await_ready. `failed-v2-*` retains that attempt separately;
it is not counted among the passing 33 executions.

## Reproduction

Run from the repository root inside the Preview 2 Linux SDK launcher. Supply
the pinned lwIP source archive using `XOS_LWIP_SOURCE_ARCHIVE`. Use new output
directories; the builders and runners intentionally reject existing fixture/test
directories. Keep inputs unchanged until the guest finishes.

```sh
python3 tests/launch_control_host.py --output build/launch_host
python3 scripts/build.py --output-dir build/launch_system --quiet-demos-on-launch
python3 scripts/build_launch_control_probe.py --sdk build/launch_system/sdk --output build/launch_fixture
python3 tests/launch_control_guest.py --system build/launch_system --fixture build/launch_fixture --output build/launch_guest --repeat 3
```

The public weak wait hook is part of libxos when launch control is linked. The
native cases would deadlock with a direct blocking sys20 during child PREPARE
or READY; the multi-child case also requires pumping the other controlled peer.
The owner quota remains four channels. No process-tree authority, durable
revocation, GNU shared-runtime combination, or live upgrades are claimed by
this module's evidence.
