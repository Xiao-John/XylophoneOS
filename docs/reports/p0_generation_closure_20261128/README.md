# Current P0 generation closure

The fresh Preview 2 composition passed **21 generation checks in three rounds,
including 12 actual public GNU C launches**, on native system
`ec96cc19110d9906`. Every round restored exactly **129793 free pages /
2 tasks / 0 completions**. No production change was required by this run.

The controller first launched the approved initial closure. It retained an
old immutable pin while activating another approved generation, rejected a
stale sequence, rejected an approved but missing-main candidate while keeping
the current generation usable, rolled back, and rejected admission after
revoking both an inactive and the active generation. Every successful launch
executed real GNU constructors, relocation, TLS and the supplied environment
through ordinary public inspect/spawn/wait and authenticated READY/ACK.

`qualification.json` records exact SDK, system, GNU producer, executable and
root identities, the three actual rounds and replay instructions. The public
GNU producer completed all 75 recorded build steps using ordinary GNU
`make lib`. Its build-only status remains unchanged; guest execution has its
own result. The root-2 missing main is deliberately absent.

`source_bindings.json` binds 392 unique producer, launcher, probe and runner
source files. Each was compared with both the working bytes and the immutable
producer commit before export. All nine GNU artifacts, installed C payloads,
root snapshots, launcher/probe artifacts and input receipts were also checked
again. The native SDK's file-only and files-plus-directories tree algorithms
are identified separately. No path or later artifact was substituted into an
older result.

`host_checks.json` retains 23 production closure/ELF scenarios in ordinary and
ASan/UBSan modes, 46 passes. That earlier host run used `7d4489d`; all 55 source
inputs are unchanged at the final producer revision. Modeled Files OFDs and
unknown-outcome cases in that test remain host evidence. LeakSanitizer was
explicitly disabled under the SDK launcher. The three native rounds above
provide the actual activation, pin and lifetime observations.

The exported summary keeps necessary source/artifact identities and results;
raw local receipt digests identify its origin. It excludes host inventories and
serial transcripts. A flat root manifest binds the report leaves. The scope is
a bounded, volatile, per-controller catalog. Persistent/global provisioning,
cross-descendant revocation, process-tree budgets, power-loss recovery and
online dynamic-library loading remain separate capabilities.

## Public source mapping

The recorded local producer `1b8b0ae1cc1fc29bfde69b4f0d69f49a9b8a39d0` and
[public source `0056c9fa`](https://github.com/Xiao-John/XylophoneOS/commit/0056c9fad097dddfeede319ff7c63b3ebd2bfcd5)
have the identical complete Git tree `3c67a6f4ce7ee0061af3ef743c07b9d6757f1fb1`.
The public commit tree was read from GitHub and matched to the local Git
object. Thus all 392 recorded producer/runner files have a public source
location. The original revision and raw receipt identities remain unchanged.
The earlier host test keeps its own `7d4489d` source identity.
