# Sequential ELF metadata: renewed closure qualification

The production parser change `7287757c` (imported as `47e5ab91`) passed all
**42 actual host executions**: 21 ordinary and the same 21 under AddressSanitizer
and UndefinedBehaviorSanitizer. This new run uses the changed parser bytes;
the prior recovery report remains unchanged and is not relabeled.

The parser now checks the complete bounded dynamic string table, then dynamic
symbols, then symbol-version indices in sequential passes. This removes the
single pinned 4 KiB cache's repeated switching between symbol/string/version
tables on genuine libstdc++. The change uses a bounded local 4 KiB buffer,
preserves the original same-read/context object identity, and leaves the
absolute startup deadline and public pin ABI unchanged.

The fixtures are SDK-built real ET_EXEC/ET_DYN/PIE inputs with dependency,
relocation, TLS and version metadata. The production closure, generation,
digest/identity, static ELF and dynamic ELF verifiers are linked directly;
only Files OFDs are modeled with immutable snapshots and injected uncertain
transport results. Seven semantic ELF mutations are reapproved at the digest
layer before validation: NEEDED, SONAME, W+X, RELRO, relocation target, TLS
alignment and version hash. All are still rejected by the real parser.

The remaining cases cover initial root approval, SDK identity, the same pinned
object after namespace changes, absolute deadlines, failed activation without
state change, rollback, stale updates, revocation, and ownership retention after
unknown open/read/close results. This is a new host qualification, not native
GNU C++ startup qualification. That integration must rebuild the SDK/runtime
and run against the new exact native bytes.

`report.json` retains all source hashes, actual target ELF hashes, commands,
tool identities and per-case results. `ordinary.log` and `sanitized.log` are
the corresponding actual per-process logs concatenated in report order.
`conversion.json` records the unpublished raw report identity and mechanical
environment-path conversion. The exported leaf hashes occur only in the flat
root `manifest.json`; git authenticates that root.

Reproduce inside the Preview 2 SDK from this source:

```sh
python3 tests/dynamic_closure_host.py --output build/dynamic_closure_sequential
```

Use a new output directory. `${XOS_ROOT}` denotes the checkout,
`${XOS_PREVIEW2_PREFIX}` the SDK tool wrapper/prefix, and
`${XOS_PREVIEW2_CELLAR}` its packaged dependencies. These are explicit replay
templates rather than claims that one host's absolute paths are portable.
