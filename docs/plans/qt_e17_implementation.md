# E17 / G05 implementation and reproduction

2026-10-29. Source plan: upstream Draft PR #12, head `9ce25786eb2d913a6579430718118c4e62d05c93`,
read in full; still open/unmerged at start. This implementation starts at upstream
`c39cef1f365bf5944b7dce920c304ae396cbb49b`, not the planning branch. The plan file is
not duplicated. Final qualification and failures are recorded in work log 0078.

## Build

QtBase v6.8.3, tag commit `c07c2d5a527a644d36e7853d55132ae38921682f`; archive
SHA-256 `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`.
`prepare_widgets_source.py` replays the unchanged E15/E16 patches in a new tree.
`configure_widgets.py` enables actual Widgets, Gui, FreeType and HarfBuzz. It
explicitly disables the unsupported file-dialog feature; the initial link failure
from pathconf/getpwnam is preserved. No pretend POSIX success functions were added.
E15/E16 configure/build entry points and frozen reports are retained.

Rebuild the current threading SDK/C++ runtime with `build_threading_sdk.py` in a
private output. Configure and build all target Core/Gui/Widgets together against
that SDK; do not link the frozen E15 Core into this profile.

```sh
python3 src/ports/qt6/prepare_widgets_source.py "$QT_ARCHIVE" "$NEW_SOURCE"
python3 src/ports/qt6/configure_widgets.py --source "$NEW_SOURCE" \
  --build "$NEW_BUILD" --sdk "$CURRENT_SDK" --binutils "$TARGET_TOOLS" \
  --host-qt "$HOST_QT_683"
cmake --build "$NEW_BUILD" --target Widgets --parallel 6
python3 src/ports/qt6/build_widgets_fixture.py \
  --source src/ports/qt6/editor/main.cpp --sdk "$CURRENT_SDK" \
  --qt-build "$NEW_BUILD" --core-build "$NEW_BUILD" --qt-source "$NEW_SOURCE" \
  --host-qt "$HOST_QT_683" --binutils "$TARGET_TOOLS" \
  --output "$NEW_APP/notes.elf"
python3 scripts/build.py --output-dir build/qt_e17/NEW_SYSTEM
```

`build_aurora.py` also builds the reusable `libXosAurora.a` separately. The ELF
builder records actual commands, dependencies, SDK archive hashes, Qt archives,
resources and ELF. Host moc/rcc are 6.8.3 generators; all application/library code
is cross-compiled for XOS. `--no-undefined`, no host Qt/libc, one static QPA plugin.

## QPA and interaction

The minimal QApplication + QLabel + QPushButton + QPlainTextEdit probe is real.
Its viewport/scrolling and ordinary editor repaint calls use the top-level backing
store with offset (0,0). Trace records `same`, offset and dirty rectangle count.
No child/offset workaround or rendering suppression was necessary. Existing
native-child/nonzero-offset and second-top-level rejection remain explicit.
Home/End/PageUp/PageDown/Delete extend the existing Set1 mapping; existing English,
modifiers, PS/2 mouse and joinable input-thread lifecycle remain in place.

The editor has one full-screen native top level. Path input, confirmation, error
and save state are children of that window. Ctrl+O focuses the path, Enter opens,
Ctrl+S saves, Escape requests exit. Modified/unknown documents require inline
Save-and-continue/Discard/Cancel. Context menus/dialogs and clipboard/IME are not
advertised. File size is limited to 1MiB; mixed/bare CR, invalid UTF-8/NUL and
Unicode separators that QTextDocument would normalize are rejected before load.
UTF-8 BOM, uniform CRLF, LF and trailing-newline state are retained. DejaVu glyph
coverage is not full Unicode/CJK font qualification.

## Saving and the precise safety boundary

QFile loads text and verifies readback. QFile WriteOnly/truncate is never used to
save. QSaveFile's source ignores sync failure and the XOS rename endpoint is not
POSIX atomic overwrite; a real guest probe confirms existing-file replacement
cannot be used as the safety contract. Direct-write fallback stays disabled.

The editor uses existing file wire-v2 begin/chunk/sync/commit/sync operations.
An existing target is opened writable without truncation and closed before staging
so FatFs read-only errors are checked. All chunks and precommit sync are checked;
failed precommit writes abort staging and leave the old target unchanged. Commit
or final-sync errors are conservatively **UNKNOWN**, keep the buffer dirty, and
block retry until recovery. A real boundary-injection case observes complete new
bytes after a reported commit error: it is deliberately not called “old retained”
or “save succeeded”. No general old-path guarantee is claimed after an unknown
commit. Successful saves require sync and exact QFile byte readback.

The file service's existing journal/backup recovery is reused, not reimplemented.
Consumer-side stale-file comparison is not a concurrent-writer CAS. No claim of
arbitrary power loss, torn-sector safety, complete POSIX transactions or static
binary distribution is made.

## Tests

All output directories below must be new. Runners verify receipts before starting.

```sh
QEMU="$QEMU_BIN" python3 tests/qt6_widgets_acceptance.py \
  --image "$IMAGE" --payload "$ELF" --case interactive --output "$NEW_CASE_DIR"
```

Other cases: `lifecycle`, `no-vga`. Additional runners: `qt6_widgets_probe.py`,
`qt6_aurora_acceptance.py`, `qt6_save_acceptance.py`, `qt6_editor_errors.py`,
`qt6_widgets_resources.py`. Save-failure fixture links explicit `--wrap` symbols
recorded in its receipt; it is test-only and not the editor ELF. Read-only/full
are actual disposable FAT states; partial staging is an actual shorter request;
close/sync/commit status failures are guest consumer-boundary injections.
`qt6_block_faults.py` additionally arms a QEMU blkdebug filter through QMP after
staging and tests actual block write/flush EIO, then clean reboot. This is not a
physical-media or power-loss test. These real storage errors leave same-boot
file read/sync failed; the validated recovery path is clean reboot, not live retry. The killed-staging process/reboot case uses real process
termination and file-service cleanup. Original failed scripts and screenshots are
retained separately from accepted runs.

The same system re-runs G02, current-profile G04, freshly linked G01/G03 probes,
thread/pthread/C++/file/persistence gates. QtQuick/QML, multi-window, SMP, absolute
memory peak, long randomized stress and full distribution/relink review are NOT_RUN.
