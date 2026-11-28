# Dynamic closure recovery: real ELF host qualification

**42 passed executions:** 21 independent cases, each ordinary and under
AddressSanitizer/UndefinedBehaviorSanitizer. The production closure, generation,
identity/digest validator, static ELF parser and public dynamic ELF parser are
linked directly. Only the Files boundary is modeled as immutable open-file
description snapshots with injected uncertain transport outcomes.

This is host qualification. The ordinary GNU libc/libstdc++ native guest,
actual Files descriptor transfer, GNU rtld and constructors remain the separate
public-runtime integration gate. This report does not turn modeled Files calls
into a claim of native execution.

## Inputs and scope

The Preview 2 target compiler/linker produced a native ET_EXEC bootstrap,
ET_DYN interpreter, PIE executable and a versioned shared library with a real
TLS symbol. The main executable has a real DT_NEEDED/PLT relocation and the
library uses the C++-style SONAME `libstdc++.so.6` to exercise the permitted `+`.
These small ELF inputs are not GNU libc or libstdc++ implementations.

The actual parser detects all seven metadata negatives: changed NEEDED,
changed SONAME, a writable/executable LOAD, removed RELRO, an unmapped relocation
destination, invalid TLS alignment, and a malformed version hash. Each mutated
file's digest and approved manifest root are recomputed before configure, so
these cases reach semantic validation rather than failing the outer hash check.

Other cases cover one-time approved policy installation, wrong SDK identity,
initial verification before publication, immutable pins after namespace changes,
exact path fallback, verified activation/rollback, stale updates, current
revocation and recovery, unchanged active policy after failed candidate checks,
and finite deadlines. Unknown open/read/close outcomes keep ownership or the
unknown-operation quarantine and are never replayed. Successful release is
idempotent and preserves generation/ticket metadata for commit-failure cleanup.

The real PIE fixture exposed a valid empty GNU-hash-table case; the parser fix
is `dd698dfa` (imported here as `312d21b9`). The qualified controller/closure
source is `6006225b`, and test sources are checkpoint `302161d3`. Exact source
bytes, target ELF hashes, commands, tool identities and individual results are
in `report.json`; both model logs are retained as plain text.

`manifest.json` is the only per-directory hash root and covers every other leaf.
`conversion.json` records the raw, unpublished report hash and environment-path
conversion; output hashes belong only to the root manifest.

## Reproduce

Run from a matching repository inside the Preview 2 SDK launcher:

```sh
python3 tests/dynamic_closure_host.py --output build/dynamic_closure_host
```

Use a new output directory. The runner builds all target ELF fixtures, compiles
both model binaries, runs each case in a fresh process, checks all input bytes
again and writes its receipt. Public command templates use `${XOS_ROOT}` for
the checkout, `${XOS_PREVIEW2_PREFIX}` for the SDK target-tool prefix and
`${XOS_PREVIEW2_CELLAR}` for the SDK's packaged compiler/dependency directory.
The SDK launcher resolves the actual compiler environment; these are explicit
replay input templates, not commands to execute without resolution.
