# Current native P0 integration

The rebuilt candidate **7c8c59058be0b5f1** passed the ordinary smoke, license,
current ABI and four native integration gates. The eight fixture/guest commands
all exited 0. This is a fresh integration result from the Preview 2 development
environment, with QEMU TCG and pipe transport.

| Gate | Observed result |
| --- | --- |
| Ordinary smoke | 79 checks across 10 suites |
| Registered license materials and SDK copies | 10 materials; 0 active open items |
| Current ABI documentation | 26 named operations match current headers; syscall-number uniqueness passed |
| Authenticated launch control | 33 cases: 11 modes in each of 3 rounds |
| IPC lifecycle, authority and quota | 12 mode runs: parent/lifecycle/authority/quota in each of 3 rounds |
| IPC deadlines | 3 rounds, each checking all 6 deadline conditions |
| Static stdio compatibility | 45 cases: 15 per round, including 12 actual native target executions |

Every round/case in the four native integration suites restored **129793 free
pages / 2 tasks / 0 completions**. The stdio run also preserved the seeded file.
Its probe explicitly links production `load.cpp` before the native SDK
archives. The separate [packaged glibc SDK pipe gate](../p0_sdk_pipe_closure_20261128/README.md)
uses the delivered `libxos_terminal.a` without that object override.

The six deadline conditions cover receive timeout with a live peer; send
timeout with payload preservation; immediate/expired deadlines with readiness
checked first; unsupported scope and legacy rejection; readiness waking receive
and send; and close waking both sides with no arithmetic wrap and final timeout
semantics. All six conditions were observed in each of the three guest runs.

## Source and result binding

The original producer revision is
`3964200d524fd39f3a95c166800832623c5f3591`. All **2211** system source entries
were compared by SHA-256 with
[public commit 819ea63](https://github.com/Xiao-John/XylophoneOS/commit/819ea63ae84b1e89862648af002c2a09d1936c02);
all match. This mapping covers the recorded build inputs. The original
producer identity and its distinct history remain in `qualification.json`.

The source digest is
`7c8c59058be0b5f1ab85450ad69a0c1409fb04f0f3af2b234a6eca645dcb2260`;
the ordinary ISO digest is
`ab2b8f11de13e433705c8965d4437df72a6c6308af260844a810ef2e722e7f51`.
The JSON records the system/SDK manifests, fixture receipts, original result
digests and individual outcomes. Independent review matched all four native
summaries to the original receipts, checked their fixture ELF bytes, matched
all ten ordinary reports and their 79 checks, and checked the license and ABI
results. It also repeated the 2211-file comparison against the public Git
objects and checked the frozen ISO and manifests.

This minimized report does not include host inventories or raw serial logs.
The flat `manifest.json` covers every report leaf. Network, public GNU runtime,
frozen SDK rollback and distribution receivers keep their separately bound
results; this report does not change their source or artifact identities.

## Replay

Use a checkout with the recorded source inputs inside the checksum-pinned
`xos-sdk-preview-2` environment. Its archive SHA-256 is recorded in the JSON.
Use the ordinary launcher and `/bin/bash -c`. Provide `clang++` and `lldb`
19.1.7 on PATH for the second-ISA and symbolic-debug checks. This run supplied
signed Debian trixie packages separately; it did not modify the original SDK.
AddressSanitizer and UndefinedBehaviorSanitizer ran in the process boundary
suite, with LeakSanitizer explicitly disabled.

From the checkout root, the native system and ordinary gates can be replayed
with the following commands. `make -o build smoke` preserves the selected
quiet-demo system and also invokes its license audit.

```sh
export XOS_QMP_TRANSPORT=pipe
export ASAN_OPTIONS=detect_leaks=0
python3 scripts/build.py --quiet-demos-on-launch
make -o build smoke
python3 tests/abi_doc_consistency.py --output-dir build/p0_replay_abi
bash docs/reports/p0_integration_final_20261128/replay.sh build
```

`replay.sh` contains the eight fixture/guest invocations used for this result.
Its optional argument selects the system directory; with no argument it uses
the recorded frozen candidate at
`build/candidates/p0-final-20261128-r2/system`. Every fixture and guest output
stays under the producing checkout's `build/` directory. Use fresh output
directories; the script refuses to replace an existing run. A new replay
creates new receipts and must retain its own resulting artifact identities.

## Earlier attempts and retained limits

An initial fixture invocation selected an output outside its producer's
allowed build directory. The script rejected it before a guest ran. The
corrected eight commands used fresh allowed directories and all passed.

The first candidate also exposed a stale zlib source-lock digest in the
license register after the source URL repair.
[PR 423](https://github.com/Xiao-John/XylophoneOS/pull/423) corrected that
registered digest. The system was rebuilt and the candidate gates rerun; the
failed attempt is not counted as a pass.

Zero active open license items refers to the audit's registered scope. Its
register still has one deferred and seven not-applicable entries with their
existing evidence and limits; those statuses are not relabeled as resolved.

The two IPC reports retain explicit-channel inheritance stress and
terminal/display/interactium regression as `not_run`. The top-level JSON
also retains LeakSanitizer, optional offline namespace mode, physical
hardware, process-tree budgets, persistent/global generation provisioning
and the listed network composition gaps. None is promoted by this native
integration result.
