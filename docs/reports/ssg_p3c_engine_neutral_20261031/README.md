# P3C: bounded, engine-neutral source observation

This draft adds a user-space watch loop over the two existing, independently
prewired P3B providers. Browser and Notes remain actual XOS processes. Their
adapters retain the existing page and UTF-16 range protocols; the scheduler and
source state machine depend on the generic provider contract rather than
liteHTML, Qt Widgets or a future browser engine. This is a scoped prototype,
not a production broker, a desktop-wide permission model, a global snapshot or
a WebKit integration. See the [contract](../../contracts/ssg_p3c_watch.md).

## Acceptance status

| Acceptance | Status | Actual scope |
| --- | --- | --- |
| `P3C_ENGINE_NEUTRAL_CONTRACT` | `PASSED_SCOPED` | Generic scheduler and state machine plus 32 synthetic guest contract checks on the framed retry build. |
| `P3C_DUAL_SOURCE_WATCH` | `PASSED_SCOPED` | Two real providers, sequential bounded pulls and source-local events in QEMU. Output is console-only. |
| `P3C_NOTES_CHANGE_EVENTS` | `PASSED_SCOPED` | Two separately injected edits with owner digests and reconstructed IPC; Browser unchanged. |
| `P3C_BROWSER_CHANGE_EVENTS` | `PASSED_SCOPED` | Two scrolls with independently recomputed geometry/visibility, and reload with old-reference refusal. |
| `P3C_PERMISSION_INVALIDATION` | `PASSED_SCOPED` | Owner revoke, document/ancestor protection and repeated observations; alternative-role/range probes in the P3B compatibility path. |
| `P3C_SOURCE_FAILURE_ISOLATION` | `PASSED_SCOPED` | Either provider exit and an injected Notes request timeout while Browser continues. |
| `P3C_ADAPTER_SUBSTITUTION` | `PASSED` | A limited synthetic replacement runs the same scheduler; unsupported geometry, replacement, invalidation and cancellation are checked. |
| `P3C_WEBKIT_READINESS` | `DOCUMENTED` | [Requirements and actual upstream state](webkit_readiness.md); `WEBKIT_INTEGRATION=NOT_RUN`. |
| `P3C_GUEST_STRESS` | `PASSED_SCOPED` | The final build completed 24/24 sessions; the earlier build's 23/24 result and capped observation remain recorded. |
| `P3C_PERFORMANCE_COMPARISON` | `PARTIAL` | Two measured modes and one common scroll; the third mode, CPU time and absolute peak memory were not measured. |
| `P3C_PUBLIC_EVIDENCE_SCAN` | `PASS` | Decoded records, archive members, changed staged blobs and proposed PR body were scanned. |
| `P3C_GUEST_REGRESSIONS` | `PARTIAL` | The final compatibility suite and affected Browser/Notes/P1 suites pass; two earlier Notes shutdown failures remain unresolved and are retained. |

An event's `SOURCE_UNCHANGED` means only that the adapter's observed,
successfully compared fields did not change. A revision is not a clock or a
grant; an empty epoch/revision means unknown or unavailable. Observation windows
are per source and sequential; `globalAtomicSnapshot=NOT_IMPLEMENTED`. Polling
can miss intermediate changes between observations. A full new baseline is
required after a continuity gap. There is no event queue, durable subscriber
pipe, replay, transparent restart, compositor-occlusion guarantee or background
input. The shared console is not an authenticated transport; framing checks
length and sequence but does not detect every same-length corruption. Synchronous
output and the scope of cooperative cancellation are described in the contract.

The framed retry build has two additional targeted guest checks. In a real
synthetic Notes process, a test-only one-shot capped response caused one
recorded retry and a complete revision-consistent reread. A persistent capped
response caused exactly two retries per observation, left Notes unknown and
published no partial document. In each check, two synthetic console-noise
records actually appeared between event-frame parts; the independent decoder
reconstructed the complete framed stream. This is scoped fault-injection
evidence, not proof that every console writer or guest configuration is covered.

## Real guest observations

The framed retry build's validation runner completed all 12 synthetic-input
scenarios, the 32-check contract probe and targeted capped-fault tests. In the
edit case the independent verifier reconstructed each Notes range transaction,
checked three distinct revisions and matched the original, `z`-prefixed and
`zx`-prefixed text to the real owner's SHA-256 records. It checked that Browser
IPC remained unchanged. For the two PageDowns, the checker recomputed scroll,
window geometry and visibility changes from the actual pages rather than using
fixed node-change counts. Reload produced a new Browser epoch and the old node
reference was refused.

After each restriction the current Notes payload was absent; a second watch
cycle did not republish it or claim unchanged. A separate compatibility test
checked fresh snapshots, another role and direct range requests against the
same provider code. Either provider could exit while the other continued. In a
separate injected Notes wire timeout, the Browser completed the next cycle and
the aggregate remained partial. During a stalled range request, a test pipe
requested stop; 1,023 staged UTF-16 units were discarded and both children
were reaped normally. The concrete `--watch-control-stdin` delegation path is
not itself guest-qualified; the test exercised the same worker using an
independent test pipe.

The normal supervisor and ordinary Browser/Notes also completed three cycles
without diagnostic frame output. That run is recorded as `OBSERVED`, without an
independent per-run DOM or raw IPC oracle. A source's complete observation is
`UNVERIFIED_AFTER_OBSERVATION`; it is not an assertion that both applications
were simultaneously current. The single-Surface platform keeps one real source
hidden and without input. No two-visible-window or background-input result is
claimed.

## Failures and lifecycle limits

Two real synthetic-session runs failed during Notes shutdown on an earlier P3C
build: one watch revoke run and one legacy-mode document-protection run. Both
providers logged EOF; Notes did not exit within the 20-second shutdown bound,
was cancelled with code -9, and the supervisor returned 1. Sampled resources
were restored. Each case passed on a fresh retry, but a retry does not erase a
failure. [Failure history](failure-history.json) includes the source-bound
hashes and host-only setup/scan failures.

The preceding 24-session stress also had one capped first Notes observation;
the stream reported unknown and then `RESET_REQUIRED`, rather than claiming an
unchanged document. A later one-shot retry test exposed a long JSON event line
interleaved with Notes output and failed verification. Both failures remain in
the evidence. The current bounded retry and framed output were tested separately
as described above.

Eight instrumented original Notes sessions and eight instrumented native-join
candidate sessions subsequently exited normally. Neither reproduced the
failure; instrumentation can alter timing, and the candidate was **not
adopted**. The two patches in this report describe test-only copies, not changes
to the shipped provider. The older single-source Consumer exit timeout and the
new Notes shutdown failures are not proven to share a cause.
`EXIT_RACE_ROOT_CAUSE=UNRESOLVED`.

## Isolated watch stress

The final build completed 24/24 synthetic sessions in one guest boot. Each
session re-observed both sources for three cycles and injected two real
PageDowns into the visible Browser; Notes was a hidden, no-input provider.
Across the run the verifier checked 144 source observations, 48 change events,
3,168 requests and 10,871,159 IPC bytes including the protocol frame headers.
There were zero capped retries, resynchronizations, local dropped-event reports
or failed sessions. All source and supervisor exits were normal, and sampled
resource counts returned to the active-display baseline (`free=130253`,
`tasks=3`, `completions=1`) 24/24 times. The
earlier r7 run was 23/24, not retrospectively upgraded; its failed first
observation was independently checked as a later `RESET_REQUIRED` recovery.
No natural capped response occurred in the final stress run, so that run alone
does not establish the retry's effectiveness or the frequency of future caps.

The 24-session wall time was 675.305 seconds, with individual sessions ranging
from 27.177 to 28.276 seconds. The 48 host-measured intervals from immediately
before input injection to the next complete-cycle marker ranged from 5.952 to
6.067 seconds (median 5.982, nearest-rank p95 6.015). These are upper bounds
including polling, observation and diagnostic capture, not hard real-time
latencies. Browser user-page/thread samples were 7,375 pages and four threads;
Notes samples ranged from 5,404 to 5,419 pages and two threads. These are
samples, not absolute peaks. Reclaim records covered 1,101–1,119 supervisor,
7,199–7,218 Browser and 5,308–5,311 Notes pages; these are exit records, not
peak measurements. The test does not provide an exact global pipe
counter, and its hidden Notes session does not qualify visible Notes shutdown.

## Partial cost comparison

On the same image, provider binaries and synthetic inputs, the independently
checked first PageDown moved Browser scroll from 0 to 282. Two P3B observations
used 88 requests and 301,741 IPC bytes including frame headers; the first two
watch cycles used 88 requests and 301,740 bytes. These are actual captured pipe
frames, not console-log byte counts. Both paths reread complete source baselines,
so this does **not** establish an IPC reduction. The source-observation intervals
were 5.15 seconds Browser plus 0.26 seconds Notes for P3B, and 5.76 seconds
Browser plus 0.26 seconds Notes for watch; diagnostic frame capture affects
these times. Whole-run wall times have different cycle counts and waits and are
not a direct performance comparison.

The separately executed third full-baseline mode, CPU time, absolute peak
memory and general missed-update rate were not measured. False-change checks
are limited to the verified fixture and event sequence. Polling delay and
intermediate changes remain dependent on sampling. The first outer performance
wrapper exited 1 after writing its comparison because of a zsh read-only
variable; a fresh wrapper retry returned 0. Both outcomes are in the failure
history and evidence.

For scale, the Browser collector caps a baseline at 4,096 nodes and 4 MiB of
collected node data, including at most 1 MiB of text; Notes caps at 131,072
UTF-16 units and 512 KiB of encoded text. The watch retains bounded previous
and in-progress payloads and emits at most 8 KiB per event. These are code
bounds, not measured peak heap usage.

## Evidence

- [Final targeted validation](evidence/validation.tar.gz), [P3B compatibility](evidence/compatibility.tar.gz), and [capped/noisy-console fault tests](evidence/capped-faults.tar.gz).
- [Final 24-session stress](evidence/stress.tar.gz) and [preceding 23/24 stress](evidence/prior-stress.tar.gz), including the independently checked partial recovery.
- Preserved failures: [watch shutdown](evidence/failure-watch-shutdown.tar.gz), [legacy-mode shutdown](evidence/failure-legacy-shutdown.tar.gz), and [interleaved event line](evidence/failure-event-interleave.tar.gz).
- [Instrumented original Notes](evidence/diagnostics-original.tar.gz), [unadopted native-join candidate](evidence/diagnostics-candidate.tar.gz), and [affected prior regressions](evidence/regressions.tar.gz).
- [Isolated partial cost comparison](evidence/performance.tar.gz) and [first comparison with outer-wrapper failure](evidence/performance-initial.tar.gz).
- [Target build manifest](evidence/build-manifest.json), [export index](evidence/export-index.json), [test-source provenance](test-source-provenance.json), and [evidence replay](evidence/replay-result.json).
- [Source-scope and SPDX marker check](source-scope-check.json), which is not an SDK distribution audit.
- [Staged scan before adding receipts](public-scan-pre-receipt.json), [full scan before its own receipt](public-scan-full-pre-self.json), and [PR-body scan](public-scan-pr-body.json); the complete index was scanned again afterward.

Archives contain synthetic inputs only. Their embedded manifests record original
and exported member hashes; host-specific paths are replaced with explicit
templates and tracebacks are omitted. The exporter scans member names, contents,
decoded IPC/oracle frames and decoded P3C events before writing an archive. Raw
local captures remain local. The previous stress runner was recovered to
[r7-stress-runner.py](r7-stress-runner.py) with the exact recorded hash; its
verifier is preserved in source commit `3852fed5c8404aab12d590e83ca64a0a1b51638e`.
The exported archives passed 73 host replay checks, including both stress runs,
the retained partial recovery and the preserved event-interleaving failure.
Replay checks the recorded evidence; it is not a new guest run.
[SHA256SUMS](SHA256SUMS) covers the evidence directory and supplemental report
artifacts; this README and later scan receipts are outside that checksum set.

The exported evidence can be checked in a fresh `build/` directory without a
guest boot:

```sh
python3 scripts/replay_ssg_p3c_evidence.py \
  --evidence docs/reports/ssg_p3c_engine_neutral_20261031/evidence \
  --scratch build/p3c-evidence-replay --output build/p3c-evidence-replay.json
```

## Build and reproduction

The target was cross-compiled with GCC/G++ 16.2.0, Qt 6.8.3 and the existing
threaded SDK. The build manifest records exact input and ELF hashes. Its
`base_commit` is the pre-build checkpoint; source commit
`4eb79a623b25c5ba3fe1addb9d6dba436a05e549` has the same recorded target-source
bytes. Browser and Notes ELFs, Qt/SDK and the
read-only guest image were reused from P3B; no new kernel image was built.
The guest was x86-64 QEMU 11.1.2 TCG, one CPU, 512 MiB, with the synthetic
fixture and no real user documents. Host contention occurred during some
functional tests, so their wall times are not benchmark results.

With independently obtained matched inputs, set `QEMU`, `XOS_IMAGE`,
`XOS_SDK_PREFIX`, `XOS_BUILD_DIR`, `XOS_QT_SOURCE`, `XOS_HOST_QT`,
`XOS_BINUTILS`, `XOS_P3B_BUILD_DIR` and `XOS_P3C_BUILD_DIR`. Choose fresh output directories under
`build/`. The P3B build used for the comparison must come from the recorded
PR #11 baseline, not an assumed later source tree.

```sh
python3 scripts/build_ssg_p3c.py --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --host-qt "$XOS_HOST_QT" --binutils "$XOS_BINUTILS" --output "$XOS_P3C_BUILD_DIR"
bash scripts/run_ssg_p3c_validation.sh "$XOS_P3C_BUILD_DIR" "$XOS_P3B_BUILD_DIR" build/p3c-validation
bash scripts/run_ssg_p3c_compatibility.sh "$XOS_P3C_BUILD_DIR" "$XOS_P3B_BUILD_DIR" build/p3c-compatibility
bash scripts/run_ssg_p3c_performance.sh "$XOS_P3C_BUILD_DIR" "$XOS_P3B_BUILD_DIR" build/p3c-performance
python3 tests/ssg_watch_stress_guest.py --image "$XOS_IMAGE" \
  --supervisor "$XOS_P3C_BUILD_DIR/supervisor-test/supervisor-test.elf" \
  --browser "$XOS_P3B_BUILD_DIR/browser-test/browser.elf" --notes "$XOS_P3B_BUILD_DIR/notes-test/notes.elf" \
  --browser-receipt "$XOS_P3B_BUILD_DIR/browser-test/browser.portable.receipt.json" \
  --input tests/fixtures/ssg_browser/p2f.html --count 24 --output build/p3c-stress
```

The underlying Browser, Notes and P1 suite was rerun with the existing P3B
artifacts and returned zero failures after a preflight prefix correction. The
new supervisor was separately checked in its legacy P3B modes. No kernel,
public ABI, QPA, driver, clock, IRQ, scheduler, global permission or LocalPilot
change is part of this branch. The reused SDK's complete source/distribution
material audit remains incomplete: `DISTRIBUTION_NOT_QUALIFIED`.
