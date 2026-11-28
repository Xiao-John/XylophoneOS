# Final public-runtime generation qualification

The final composition passed **21 generation checks in three native rounds,
including 12 real public GNU C launches**. Every round returned to exactly
**129778 free pages / 2 tasks / 0 completions**. All results use newly built
artifacts after both the capsule collision and constructor/READY fixes.

## Exact final composition

Native production, controller, launcher, probe, program producer and GNU producer
source are fixed at `299ea47cc991fb781e8671c41213a02c169f4130`. The system build is
`faad61f4f20be0f7`; the public GNU producer is v5 and the C stage is C5. The source
export is complete and has no overlays. Its 8,837 Git files were rechecked after
execution. The source binding independently verifies 71 launcher/program/runner
inputs, 375 unique GNU producer source inputs and all nine actual GNU producer
artifacts against their recorded identities and the immutable Git revision.

The C SDK was independently approved with manifest
`59e9daf663168bb591479434f373ad9616e19b8dab155d6a2c1a1d461d4aa95a`
and tree
`a1109d8caad10d6a921aeae9d74ed4e3d8e648b3cf3c9adc7c5f4c9edce12a31`.
The native SDK manifest is
`fc8b81adef3b0397bb7743093091ffc21d07f14c6a33504e1d087d11e8601ffa`.
Its entire 239-file, 12-directory snapshot used by C5 matches the actual native
system SDK, including archive provenance. The cross-binding records both the
file-only and files-plus-directories inventory algorithms separately.

The actual three-root launcher ELF is
`150c0a59460db3f673f99951923880363c0955833bcc1e2dcbbc933e4cce5bfd`;
the native R2 probe is
`79b3e9620830b822d68e63dfdf5e9e6264dbfea3a0abb9d004e5d0dab62a4872`.
The public native ABI identity is
`6742293901e0c560b8232b7c29ec44e13348e03903942ac8e1c387a0ac92111d`.

| Approved slot | Manifest SHA-256 | Purpose |
|---|---|---|
| 0 / generation 1 | `76b190d753bad80ffd0ada8e13572e4fc3a4234e7fc7ece5493009c443a02148` | Initial complete final C closure |
| 1 / generation 2 | `a27c69b2427e5ad9c3cc723ea4c0387203041545e564385737a5fa44b665a2fd` | Alternate main path using the same actual C5 ELF |
| 2 / generation 3 | `866434f172d32f122a0baa5dcb6aa721ff449e2f16aaf0d821a008e59c1d4c79` | Approved manifest with deliberately absent main |

The actual installed main is
`f3c9fba2a02ae7603dcbf2dc28f54acd91efbd5922f5f5ec956646b5f6a938ba`.
The final installed libc is
`0abbf40192c882914c686c0628537bf4264cf11a32b282d7de897f65c9532917`;
the interpreter is
`40bf51f79a8d529044cee4b9f929b94f58f9f64667b357791f37551a325ce7b2`.
Complete payload, bootstrap and source identities remain in the build receipts.

## Actual generation behavior

One native controller retains its volatile policy throughout each round:

1. Install slot 0 and launch its real public C program.
2. Keep an old immutable pin readable while activating and launching slot 1.
3. Reject a stale sequence without changing the active generation.
4. Reject the approved missing-main candidate, preserve slot 1 and launch it again.
5. Roll back to slot 0 and launch it again.
6. Revoke slot 1 and reject subsequent admission.
7. Revoke active slot 0 and reject future capture with the no-active state.

Each round finishes at sequence 5 with revocation bitmap 3. Its four actual C
launches use ordinary public inspect/spawn and `sdk::wait_flags`. They execute
real GNU constructors, relocation, TLS and the supplied environment, complete
the authenticated startup protocol, and exit normally. Files pins, loader
cleanup, channel operations and resource accounting are actual guest behavior.

The [final native lifecycle qualification](../p0_final_native_20261128/README.md)
uses the same source and system for controller, IPC lifetime/authority/quota,
deadlines and strict static-stdio regression. Public C++/worker constructors and
same-PID exec have their own final runtime qualification rather than being
inferred from these C generation cases.

## Replay and evidence

Build `scripts/build_dynamic_launcher.py` with the exact native system/source,
the independently supplied C SDK manifest and tree digests, and three explicit
local manifest files plus their approved guest paths. Build the probe using
`scripts/build_dynamic_generation_probe.py` against that launcher's immutable
root header. No guest-adjacent JSON authorizes a new generation.

Run `tests/dynamic_generation_guest.py` with the resulting launcher and probe,
C5 program stage, complete public GNU v5 build, exact producer revision above,
a read-only Git object source, the same SDK anchors, `--repeat 3`, and a new
output directory. All producer source files used by the program stage are
materialized from that Git revision. System, SDK, sources, roots and installed
payloads are verified before and after execution; the additional native
cross-binding is independently repeated after the guest succeeds.

The build receipts retain their actual build-only status. Execution is recorded
in the separate guest report and full serial/per-round transcripts. Complete
GNU and C program producer receipts are included. `conversion.json` records
unpublished raw byte identities and the exact path/text transformations. The
flat root `manifest.json` alone hashes exported leaves.

This closes P0's volatile single-controller generation activation, rollback and
revocation gate for the final source and these exact artifacts. Earlier C4/v4
and capsule-version-1 qualifications remain historical and are not relabeled.
Durable policy, cross-descendant revocation and process-tree budgets remain P1.
