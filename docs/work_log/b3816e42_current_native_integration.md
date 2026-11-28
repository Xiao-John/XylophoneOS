# Current native P0 integration

The corrected candidate `7c8c59058be0b5f1` now has one minimized native
integration record at
`docs/reports/p0_integration_final_20261128/`. It preserves producer
`3964200d524fd39f3a95c166800832623c5f3591` and records that all 2211 system
source files match public `819ea63ae84b1e89862648af002c2a09d1936c02` by
SHA-256. Documentation history is not substituted for the original build
identity.

The original records show 79 ordinary checks, 10 registered license
materials with zero active open items, a passing current ABI check, 33
launch cases, 12 IPC lifecycle/authority/quota mode runs, three deadline
rounds with six conditions each, and 45 static stdio cases. All eight native
fixture/guest commands exited 0. Each native round/case restored
129793 free pages, two tasks and zero completions; stdio also preserved
seeded file contents.

Review matched the four native summaries and receipt hashes, verified their
fixture ELF bytes, checked all ten ordinary reports and the license/ABI
results, rechecked the system ISO/manifests, and independently compared the
2211 source hashes with public Git objects. The report includes the exact
eight-command replay with outputs under the producer's build directory and
a flat manifest covering its leaves. This evidence review did not rerun the
expensive guest suites.

The replay passed Bash syntax checking, and its eight expanded invocations
match the recorded command vectors. The flat manifest verifies all three
leaves. The actual staged five-file delta passed the public evidence path
scan with zero findings.

The initial invalid output-directory invocation remains a failed pre-guest
attempt. The initial stale zlib-lock registry digest was repaired in PR 423
before rebuilding and rerunning the candidate. Deferred/not-applicable
license entries and all recorded not-run cases retain their scope. Public
GNU runtime, networking, rollback and distribution results remain in their
own reports. This change does not update the state or plan.
