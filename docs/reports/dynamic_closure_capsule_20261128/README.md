# Bootstrap reservations: real ELF rejection and closure regression

The complete frozen production source at `3699916df590a2fe0ea9b419836ded2d9344e6b3`,
with only the two host test files from `5cc9d66d`, passed **46 host executions**:
23 ordinary and the same 23 under AddressSanitizer and UndefinedBehaviorSanitizer.
All recorded source inputs were independently compared with those exact Git blobs.

The two new negative cases use a real SDK-built static bootstrap ELF. They shift
its entry point and every nonzero program-header virtual and physical address by
the same displacement, placing its LOAD at `0x70000000` (the worker arena) or
`0x71000000` (the relocated startup capsule). Its genuine read-only identity NOTE
remains in the same LOAD. The ordinary static ELF inspector still accepts each
image. Both complete generation manifests are then updated with the mutated
object digest and explicitly approved again; the production dynamic closure
preflight rejects each with `error::bounds`, publishes no active policy, and
releases every known pin. This distinguishes the added dynamic reservation rule
from accidental malformed-ELF rejection and preserves ordinary static admission.

The original 21 cases also pass against the changed production bytes: approved
root and SDK binding, immutable pins, bounded deadlines, cleanup ownership after
unknown I/O, activation, rollback, revocation, and seven malformed dynamic ELF
metadata cases. Only Files OFDs are modeled. This report establishes host
qualification; it does not claim that the new capsule address has passed a
native guest or GNU thread test. Those require freshly rebuilt target artifacts.

`report.json` records exact source, tool and target fixture hashes, commands and
per-process outcomes. `ordinary.log` and `sanitized.log` contain their actual
outputs. `conversion.json` records the unpublished raw receipt hash and mechanical
export rules. Only the flat root `manifest.json` carries exported leaf hashes.

To reproduce, export the stated production revision into a fresh source tree,
replace `tests/dynamic_closure_host.py` and
`tests/fixtures/dynamic_closure_host.cpp` with the stated test revision, then run
inside the Preview 2 SDK:

```sh
python3 tests/dynamic_closure_host.py --output build/r2_host_capsule
```

The output directory must be new. `${XOS_SOURCE_SNAPSHOT}` is that source tree;
`${XOS_PREVIEW2_PREFIX}` and `${XOS_PREVIEW2_CELLAR}` are explicit replay templates
for SDK wrappers and packaged tools.
