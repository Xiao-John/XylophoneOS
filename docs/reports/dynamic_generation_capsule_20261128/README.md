# New capsule ABI: final native generation qualification

The rebuilt capsule-version-2 composition passed **21 checks in three complete
native rounds, including 12 real GNU C launches**. Every round restored exactly
**129779 free pages / 2 tasks / 0 completions**. These observations use freshly
rebuilt source and artifacts after the real thread-arena collision was found.
They do not relabel the earlier capsule-version-1 results.

## Exact composition

Native, launcher, bootstrap, public GNU runtime and program producer sources
are fixed at `3699916df590a2fe0ea9b419836ded2d9344e6b3`. The native system is
`c1575e2adfc6fa5d`; the new runtime is GNU v4 and the program stage is C4. The
startup capsule now lives at `0x71000000`, outside the native worker arena, and
its ABI version is 2. The native SDK ABI binds both dynamic headers.

The launcher was rebuilt from a complete matching source export without
per-file overlays or relaxed SDK header matching. The C SDK was independently
approved with manifest
`ba1996ad0c048d97be53fb532315b2d3909631d37a8f83d456e28312de9b035c`
and tree
`31344365e3639e8764be98d23d97f93494dd019ee57dd90ad49e3b2b403750da`.
The native SDK manifest is
`61d3f52a178071cd6d2809b37669b8542e6dd93f5b429b5a924807e76b3e3779`.

The actual three-root launcher ELF is
`6eee3c42f8b9e22c5d51d0157a38fbd8f5608a9362048b3797ae53e3fb902005`;
the native probe is
`40bf20d99dfd4cc41a68fc43d80ffedba37dd77820455c13a8a7f3c31d61e4fb`.
The real C main is
`4714d0da4f069f6ec6851a2db0130a09f92cd746aebc8aec6c8e7949d70930e0`.

| Approved slot | Manifest identity | Purpose |
|---|---|---|
| 0 / generation 1 | `2eef6b691f37f1eb2f9dcb71f8ba9dbc8b3b9241cc9fd6d0a65791955f46a7a9` | Initial valid C closure |
| 1 / generation 2 | `5046759305101d66839bf81cbc5032665a1b2d045635fe6262c5133091999d2e` | Valid alternate main path, same actual C bytes |
| 2 / generation 3 | `3e896e6a0d3b5bf4293ba46ca8285e777fb04df6478fe92098100850f7d1e877` | Approved manifest with deliberately absent main |

## Actual behavior

Each round runs one native controller through seven cases without replacing its
catalog: install and launch slot 0; retain and read an old immutable pin while
activating and launching slot 1; reject stale activation; reject the missing-main
candidate while preserving and relaunching slot 1; roll back and launch slot 0;
revoke slot 1 and reject future admission; revoke active slot 0 and reject new
capture with the established no-active state. The final sequence is 5 and the
revocation bitmap is 3.

All four C launches per round use ordinary public inspect/spawn and
`sdk::wait_flags`, execute the real GNU constructors, TLS, relocations and
provided environment, then exit normally. Files pins, IPC, native completion,
GNU startup and resource accounting are real guest operations. The test does
not model them.

The existing [46-case host qualification](../dynamic_closure_capsule_20261128/README.md)
also proves that reapproved real bootstraps overlapping the worker or capsule
arena are rejected by dynamic preflight while ordinary static ELF admission
remains unchanged. The separate
[final L1/L2 native qualification](../p0_integrated_lifecycle_20261128/README.md)
covers controller, IPC lifetime, authority, owner quotas and deadlines using
the same production/native source composition.

## Reproduction and evidence

Use `build_dynamic_launcher.py` with the exact native system and source, the
independent C SDK anchors, and all three explicit generation binaries/guest
paths. Build the probe with `build_dynamic_generation_probe.py`. Run
`tests/dynamic_generation_guest.py` using that launcher/probe, C4 stage, GNU v4
runtime, the stated program-producer Git revision, a read-only Git object source,
`--repeat 3`, and a new output directory. Source and artifact paths in the
receipts are explicit `${XOS_*}` replay templates.

The source and every system/SDK/stage/pin input are checked before and after
execution. Program producer inputs are materialized from immutable Git objects;
the additional native cross-binding checks the entire program-stage native SDK
snapshot against the actual system SDK. It explicitly records the different
file-only and files-plus-directories inventory algorithms without conflating
their digest values.

Build receipts retain their original built/not-run status; execution is recorded
separately in `guest_report.json` and the actual serial/round logs. The complete
public runtime and C program producer receipts are included. `conversion.json`
retains original unpublished input hashes and the mechanical export rules.
Only the flat root `manifest.json` hashes exported leaves.

This completes the P0 volatile single-controller generation gate for these exact
new bytes. Durable policy, cross-descendant revocation and process-tree budgets
remain P1. Separate GNU C++ thread/exception and same-PID exec cases are covered
by their own runtime qualification rather than inferred from the C launches here.
