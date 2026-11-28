# 9b8be9b8 P1 B/E merged checkpoint and C/D/F recovery boundary

## Scope and merged baseline

This integration record updates the global state after the authorized merges.
The baseline is `6332527ab64e92371266363f41f3247717a3cac8`.
It changes documentation only; it adds no runtime behavior or ABI.

| Change | Published pull request | Result |
| --- | --- | --- |
| Public clocks and bounded POSIX timers | #438 and #441 | Merged; issue #124 closed as completed. |
| Bounded pthread joins and target-thread clocks | #440 | Merged; issue #125 closed as completed. |
| GNU/gnulib backend | #439 | Merged; issue #133 closed as completed. |
| P1-E application authority and recoverable data/installation transactions | #442 | Merged; independent frozen evidence retained. |
| P1-B cumulative budgets and observable Files uncertainty | #443 | Merged after CI; includes the nine-case integration on E. |

The GitHub issue endpoints were read after merging and all three reported
`state=closed`, `state_reason=completed`. The P1-B expected head was
`ea90682cf4ac904ad1c66263081638c22c283b69`; its workflow completed successfully
before the expected-head merge.

## Evidence verification after environment recovery

The execution volume reverted to an earlier workspace snapshot during parallel
C/D/F development. Published B/E code and evidence were recovered from GitHub.
On that exact recovered tree, these checks completed successfully:

```sh
python3 scripts/verify_evidence_index.py docs/reports/p1b_authority_lifetime/manifest.json
python3 scripts/verify_evidence_index.py docs/reports/p1e_application_persistence/manifest.json
```

The B index matched 6/6 leaves and the E index matched 16/16 leaves. This is a
byte-integrity recheck of the published results, not a second execution of those
guest suites. The actual prior B runs are 27 independent cases plus nine E-base
integration cases; E has 14 fresh-VM runs. No frozen report was rewritten.
The documentation diff also passes the staged public-path and whitespace gates.

## Open acceptance and recovery ownership

P1-C still needs its final real descendant/revocation and cold-recovery matrix.
P1-D still needs successful actual application activation plus the complete
signed-distribution rejection/interruption matrix. P1-F still needs full WebCore
page layout/paint, Qt viewport, and isolated navigation/cancel/failure lifecycle
qualification. Existing static archives, restored source and host checks do not
close these gates.

Each agent reconstructs its own isolated worktree on the merged B/E baseline.
Recovered source is checkpointed remotely as explicitly unfinished work before
large builds restart. C/D share one newly built dynamic runtime and native SDK;
F builds one static GNU C/C++ SDK and the required C++ dependencies. Missing
build output and logs are regenerated rather than inferred from previous hashes.
The integrator alone updates `docs/state.md` and publishes/merges completed PRs.
The existing `xos-sdk-glibc-preview-3` prerelease retains its own P0 qualification.
