# Notes live range transactions — 2026-10-31

The tested path is an explicitly prewired, independent Consumer and Notes
Provider running in separate XOS processes. It is not a production broker or a
general security qualification. The document and all keyboard input were
synthetic. The regular live-range mode does not emit document frames or the
reconstructed text; full frame capture and the pause used for injection exist
only in the separately compiled test Consumer. The owner shortcuts and document
digest exist only in the separately compiled test Notes executable.

`final-r2/` contains the results for the final joinable-watchdog implementation.
The earlier archives in this directory are retained as evidence from the
previous implementation and must not be mistaken for final-build results.

| Scenario | Result | Observed behavior |
| --- | --- | --- |
| Live edit | `PASSED_SCOPED` | After two old-revision ranges, actual PS/2 input changed the editor. The old request returned `RESET_REQUIRED`; 1,023 staged UTF-16 units were discarded and the new revision was reconstructed exactly. |
| No edit | `PASSED` | The revision remained unchanged, with no reset. |
| Text observation revoked | `PASSED_SCOPED` | The owner disabled text observation; the next range and a fresh-start retry both returned `DENIED`, without text or a commit. |
| Document protection | `PASSED_SCOPED` | The owner marked the document protected; both requests returned `PROTECTED`, without text or a commit. |
| Ancestor protection | `PASSED_SCOPED` | The owner marked an ancestor widget protected; both requests returned `PROTECTED`, without text or a commit. |
| Ordinary mode logging | `PASSED` | The ordinary Consumer completed the same synthetic no-edit read without emitting frame records or document content. |
| Existing 3,623-unit range | `PASSED` | The ordinary Consumer reconstructed the previous synthetic fixture. |
| QtScene range boundaries | `PASSED` | All 13 existing guest boundary checks passed. |
| P1 pipe regression | `PASSED_SCOPED` | The full retry passed 17 checks, including the small Browser and dash controls. |

The owner changed permission using `host_allow_observation(false)`; protection
used the existing `xosSsgProtected` widget property. The test-only keyboard
shortcuts are owner-side controls and are not pipe operations. Already received
text remains prior authorized disclosure; the tested refusal prevents new
range text and invalidates the incomplete transaction. Resource counters
returned to their pre-session baseline in every case. The resource and exit
records, QEMU version, input and executable digests, response frames, owner
digests, and independent results are in the case archives. `serial-selected.log`
contains selected control and input lines; it is not presented as a raw log.
Only synthetic document text is included in the frame captures.

The first injection-control attempt used a function key that the current guest
keyboard mapping does not support; it failed before changing the owner state.
The test-only controls were changed to supported Ctrl+6, Ctrl+7 and Ctrl+8
combinations and all three cases were rerun. An initial independent verifier
also incorrectly depended on directory iteration order; sorting fixed that
verifier and the captured runs were rechecked. The unmodified failures and raw
host logs remain local and are not included here. The first full P1 run timed
out waiting for Consumer exit after it had received a valid Diff; a standalone
retry passed all 17 checks. A clean-checkout ancestor-protection run also
timed out after both `PROTECTED` responses; its retry passed. Diagnostic runs
on the previous implementation reproduced two further exit timeouts, including
one after `main` had returned. The cause of those hangs was not conclusively
established. Qt's detached worker can report completion before native thread
cleanup, so the Consumer watchdog now uses a joinable worker and waits for its
native termination. The final build passed all five cases, the full 17-check
P1 regression, and 16 additional ancestor-protection runs with independent
verification and resource recovery. This is scoped evidence, not a guarantee
that all exit races are eliminated. A build-helper edit also initially failed
on a missing Python import; the import was added and the build rerun. Attempt
counts and the limits of the diagnostic probes are in
`final-r2/failure-history.json`.

A separate clean checkout of the watchdog change rebuilt the test Consumer
and Notes with the documented environment variables and passed all five guest
cases with independent checks. It reused the existing matched SDK, Qt, image,
QEMU and Session binary. The rebuilt ELF hashes differed from the first build;
the evidence establishes behavior on this host, not bit-for-bit reproducible
builds or portability to another architecture. See `final-r2/clean-checkout/`.

## Reproduction

These commands are execution entry points, not a verbatim copy of the original
host command line. Configure the named environment variables for a matched XOS
image, Qt 6.8.3 build, SDK, host Qt tools, target binutils and prebuilt Session.
The target cross-compiler and archiver must be on `PATH`. QEMU 11.1.2 with
`pc-i440fx-10.0`, TCG and x86-64 was used. No other architecture was tested.
Use a new, empty `XOS_REPRO_DIR` underneath `XOS_ROOT/build`; do not overwrite
an existing run. The scripts create their temporary work disk and QMP socket.

```sh
export XOS_ROOT="$(git rev-parse --show-toplevel)"
export QEMU="${XOS_QEMU}"
python3 "$XOS_ROOT/src/ports/qt6/build_fixture.py" \
  --source "$XOS_ROOT/tests/fixtures/qt6/ssg_consumer_live_test.cpp" \
  --qrc "$XOS_ROOT/tests/fixtures/qt6/resources.qrc" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --host-qt "$XOS_HOST_QT" --binutils "$XOS_BINUTILS" --portable-receipt \
  --output "$XOS_REPRO_DIR/consumer/ssg-consumer.elf"
python3 "$XOS_ROOT/src/ports/qt6/build_widgets_fixture.py" \
  --source "$XOS_ROOT/tests/fixtures/qt6/notes_live_test.cpp" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --qt-source "$XOS_QT_SOURCE" --core-build "$XOS_BUILD_DIR" \
  --host-qt "$XOS_HOST_QT" --binutils "$XOS_BINUTILS" --portable-receipt \
  --output "$XOS_REPRO_DIR/notes/notes.elf"
for case in edit no-edit revoke protect-document protect-ancestor; do
  python3 "$XOS_ROOT/tests/ssg_notes_live_edit_guest.py" \
    --image "$XOS_IMAGE" --session "$XOS_SESSION_ELF" \
    --consumer "$XOS_REPRO_DIR/consumer/ssg-consumer.elf" \
    --notes "$XOS_REPRO_DIR/notes/notes.elf" \
    --case "$case" --output "$XOS_REPRO_DIR/run-$case"
  python3 "$XOS_ROOT/tests/ssg_notes_live_verify.py" "$XOS_REPRO_DIR/run-$case"
done
```

For the ordinary-mode and previous range controls, supply a standard Notes
build as `XOS_NOTES_ELF` and run:

```sh
python3 "$XOS_ROOT/src/ports/qt6/build_fixture.py" \
  --source "$XOS_ROOT/src/user/apps/ssg_consumer.cpp" \
  --qrc "$XOS_ROOT/tests/fixtures/qt6/resources.qrc" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --host-qt "$XOS_HOST_QT" --binutils "$XOS_BINUTILS" --portable-receipt \
  --output "$XOS_REPRO_DIR/ordinary/ssg-consumer.elf"
export XOS_CONSUMER_ELF="$XOS_REPRO_DIR/ordinary/ssg-consumer.elf"
python3 "$XOS_ROOT/tests/ssg_notes_live_no_log_guest.py" \
  --image "$XOS_IMAGE" --session "$XOS_SESSION_ELF" \
  --consumer "$XOS_CONSUMER_ELF" --notes "$XOS_NOTES_ELF" \
  --output "$XOS_REPRO_DIR/ordinary-no-log"
python3 "$XOS_ROOT/tests/ssg_text_range_guest.py" \
  --image "$XOS_IMAGE" --session "$XOS_SESSION_ELF" \
  --consumer "$XOS_CONSUMER_ELF" --notes "$XOS_NOTES_ELF" \
  --output "$XOS_REPRO_DIR/legacy-range"
python3 "$XOS_ROOT/tests/ssg_ipc_guest.py" \
  --image "$XOS_IMAGE" --session "$XOS_SESSION_ELF" \
  --consumer "$XOS_CONSUMER_ELF" --notes "$XOS_NOTES_ELF" \
  --browser "$XOS_BROWSER_ELF" --dash "$XOS_DASH_ELF" \
  --output "$XOS_REPRO_DIR/p1-full"
python3 "$XOS_ROOT/src/ports/qt6/build_widgets_fixture.py" \
  --source "$XOS_ROOT/tests/fixtures/qt6/ssg_range_boundaries.cpp" \
  --sdk "$XOS_SDK_PREFIX" --qt-build "$XOS_BUILD_DIR" \
  --qt-source "$XOS_QT_SOURCE" --core-build "$XOS_BUILD_DIR" \
  --host-qt "$XOS_HOST_QT" --binutils "$XOS_BINUTILS" --portable-receipt \
  --output "$XOS_REPRO_DIR/boundary-build/probe.elf"
export XOS_RANGE_TEST_ELF="$XOS_REPRO_DIR/boundary-build/probe.elf"
python3 "$XOS_ROOT/tests/ssg_range_boundaries_guest.py" \
  --image "$XOS_IMAGE" --payload "$XOS_RANGE_TEST_ELF" \
  --output "$XOS_REPRO_DIR/boundaries"
```

The standard Notes build does not define the test-control macro. The explicit
`--portable-receipt` option produces receipts containing environment-variable
command templates; its default, legacy receipt contains local paths and must
remain private. Input and ELF digests can be checked against the named dependencies.

`SHA256SUMS` covers this report and its exported evidence. For each case,
extract the corresponding `final-r2/` archive into a fresh directory and run
the independent verifier on that directory. `final-r2/provenance.json` records
the final tested hashes; the reconstructed, sanitized evidence containers are
not the original raw logs.
