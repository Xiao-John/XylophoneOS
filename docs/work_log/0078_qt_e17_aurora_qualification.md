# 0078 E17 / G05 — real Qt Widgets and Xylophone Aurora Glass

2026-10-29. **G05 and Aurora: PASSED (restricted functional qualification).**
No new XOS Release or Qt static-distribution qualification. QML/Quick are separate.

The branch/worktree starts at upstream `c39cef1f365bf5944b7dce920c304ae396cbb49b`.
PR #12 was open/Draft at `9ce2578`, read as the plan source and not merged/copied.
All existing worktrees were inspected and preserved. Qt/SDK/system output is private
under `build/qt_e17/`; terminal/ncursesw/xypm and other projects were not changed.
The user's latest instruction authorizes a feature PR because upstream write
permission is absent. No direct main push, merge or Release was performed.

## Delivered implementation

- Independent prepare/configure/build entry points enable real `FEATURE_widgets`.
  Current main's SDK and C++ runtime were rebuilt; Core/Gui/Widgets use that same
  SDK. QtBase tag v6.8.3 resolves to `c07c2d5a527a644d36e7853d55132ae38921682f`;
  the official archive reverified as `56001b905601bb9023d399f3ba780d7fa940f3e4861e496a7c490331f49e0b80`.
- `libQt6Widgets.a` and the XOS ELF genuinely link with target GCC/SDK. Actual ELF
  undefined-symbol list is empty; whole Qt-profile archive closure against SDK and
  Qt definitions leaves only linker-provided `_GLOBAL_OFFSET_TABLE_`.
- `libXosAurora.a` is separately buildable/linkable, with QProxyStyle/QPalette,
  shared eight-segment cubic corners, cached environment/blur, glass edges/sheen,
  a software pointer and limited hover transitions. Standard QPushButton/QLineEdit/
  QPlainTextEdit/QLabel use the opt-in theme; an independent consumer proves this.
  Background artwork is original generation with full prompt/conversion/hashes;
  no Apple assets or user-reference pixels were copied. Design study and draft:
  [Aurora](../design/aurora_glass.md).
- Real one-top-level editor: path/Open/Save/Exit, plain-text document, Markdown
  heading tint, cursor/character state, inline dirty confirmation and errors.
  Context menus/file dialogs/extra native windows are avoided. This is interactive
  Widgets, not a wallpaper/UI image. The supplied visual reference was a quality
  floor; real guest screenshots, not the host draft, are the evidence below.
- The actual QWidget viewport/scroll calls used the top-level backing store with
  `(0,0)` offset. No speculative child-offset repair or disabled repainting was
  needed. QPA retains its restrictions and adds only key mappings and tracing.

## Frozen products

System build `0bb7b60ae0d85953`, single-core QEMU 11.1.2 TCG, 512MiB, 800×600 XRGB8888.
Full hashes, commands, sources and receipts:
[qualification.json](../reports/qt_e17_qualified_20261029/qualification.json).

| Product | SHA-256 |
|---|---|
| Qt Widgets, 21,174,436 bytes | `daea9a7b96fb00e6f229bf220fda41a212f56cf5e0505a9935e0e5c0a71c72f3` |
| QtGui | `b447927867d309beaaf5af283e886dd7ac57d8ea21ba397f69d624c8469c558e` |
| QtCore | `3c29baee6eed7b708f09eb9c7df0d9d51803f049994c6371830ed947131e2447` |
| Aurora library | `a9c0bfe60ef2b5b9dc877fabd7d26650e6553d4655850039651d97a8246b9b10` |
| notes.elf, 31,961,352 bytes | `68134ab2f3755dd3a405457521add8e2f1a6f01b89d5a54db70f5d9c276b0581` |
| xos.img | `1f75150345382511e9e350a89a3eaa87d8b4d0ece0dfcb6a16c7639b71e7c853` |

Local application: `build/qt_e17/review_editor/notes.elf`; system: `review_system/`;
libraries: `widgets/lib/`; SDK: `sdk/`. These are not new published release assets.

## Real guest acceptance and regression

Twelve final suites passed: G05 interactive/lifecycle/no-device, independent Aurora,
minimal QWidget probe, save failures, actual editor RDO/full UI, Widgets resources,
and G04 pixels/input/lifecycle/no-device. G04 has 17 checks; G02 has 19. Same-system
thread core/pthread/C++ pass 15/10/10 checks; file/persistence pass 8/4 checks.
Twelve freshly linked current-SDK QtCore suites pass: smoke, posted/nested/timers,
quota, worker fault, persistent readback, file errors, C++/TLS/exception ABI, memory,
lifecycle, wait-word races, mutex contention and interrupt-only wake.

- PS/2 via QMP: English, multi-line, Shift selection, arrows/Home/End, replacement,
  backspace, mouse placement, long document scrolling and Ctrl+S. Actual disk bytes
  after save equal expected edited bytes. BOM/CRLF, empty and no-ending-newline
  files roundtrip; new-file creation works. Six files compare exactly after normal
  sync and restart. UTF-8 test strings include accented and Greek content; complete
  Unicode/CJK glyph coverage is not claimed.
- Dirty guard: inline Cancel and Discard, no second native dialog. Three separate
  editor launches/exits restore exact resources. Client kill/fault, thread quota,
  huge-image OOM, Display Service death/restart/fault during present and no-VGA
  retain serial rescue and expected resource return.
- RDO/full are genuine disposable FAT states and real UI save actions; old bytes
  stay unchanged. Partial staging writes actual shorter data; close/precommit-sync
  error results are guest API-boundary injections. Killing a process during staging
  retains old data after cleanup, sync and reboot. Commit-error injection observes
  complete new bytes but reports UNKNOWN, never false success or “old retained”.
  Additional QEMU blkdebug write/flush EIO was armed by a dynamic block filter only
  after the actual ELF loaded and bytes were staged. Both real ATA/file-service
  failures preserved old bytes offline and after restart. Same-boot read/sync
  remained failed after the real storage errors; serial rescue worked and clean
  reboot was required. This is not physical
  media failure or power-loss qualification. Existing production recovery code
  also passes 21 host/FatFs injected cases;
  that is explicitly host evidence, not a guest power-loss test.

Screenshots: [editor](../reports/qt_e17_qualified_20261029/review_gates/g05_interactive/aurora-open.png),
[selection](../reports/qt_e17_qualified_20261029/review_gates/g05_interactive/selection.png),
[scroll](../reports/qt_e17_qualified_20261029/review_gates/g05_interactive/long-scroll.png),
[dirty confirmation](../reports/qt_e17_qualified_20261029/review_gates/g05_interactive/unsaved.png),
[independent standard Widgets](../reports/qt_e17_qualified_20261029/review_gates/aurora/standard-widgets.png).
Raw serial/PPM/bytes are retained losslessly as `.gz` alongside reports and PNGs.

## Measured budget and limits

The targets were recorded before final visual measurement in the design study.
54 ordinary key samples: median below the 10ms clock granularity, p95 10ms, maximum
90ms. 243 presents: maximum 10ms. These are functional-run observations, not stable
real-time bounds. The two main background images use 3,840,000 bytes, cached once
on size change; initial cache construction was 210–220ms, separate from key input.
Sampled editor high water: 7,241 user pages = 29,659,136 bytes (28.29MiB), not an
absolute peak. Same ELF, scene/font/layout, three baseline/Aurora pairs: additional
sampled memory 3,932,160 / 3,964,928 / 3,932,160 bytes. Observed threads commonly 3,
including QtGui's existing worker pool; no assertion that Widgets always uses 2.
All process exits return free pages/tasks/completions exactly to their baselines.

Limits: one native fullscreen window, no system compositor/lensing, CPU raster,
1MiB file limit, valid UTF-8 text only, uniform LF/CRLF. Unsupported lossy input is
rejected before load. Concurrent-writer CAS, arbitrary disk failure/commit rollback,
physical close/media failure, power loss/torn sectors, absolute peak, CPU percentage, long random stress, hardware,
SMP, IME/clipboard, full Qt API, QML/Quick and full static-distribution/relink/member
license audit are NOT_RUN/unsupported as detailed in the report. QSaveFile is not
used as an unproven overwrite-safety contract. Saved state after commit error is
UNKNOWN; no general “every save failure leaves the old path unchanged” claim.

## Failures retained and corrected

Initial link occurred before the Widgets archive finished; later real linking
exposed QFileDialog pathconf/getpwnam dependencies. The independent profile now
explicitly disables unsupported file dialogs. No fake POSIX implementation.
The first probe attempted serial Ctrl+C although that foreground path did not
cancel it; real PS/2 Escape and normal teardown replaced the scripted assumption.
An export fixture initially refused overwriting its own host comparison output;
a new output filename fixed the harness without changing guest behavior.
The first independent-style visual review exposed palette inheritance and led to
explicit class/widget palette setup and pixel contrast assertions. A memory helper
incorrectly expected two threads; actual measurements/source inspection identify
QtGui's pool, and the report records observed counts within the existing four-thread
profile. Stale receipts during iterations were rejected before guest launch and
retained. Key timing initially logged twice via app and widget event filters;
the frozen application uses one filter and compact change counts, not full text
serialization per key. Early static blkdebug injection fired during boot recovery, before the application
could load; the service failed closed. The final runner arms the filter through
QMP after staging, preserving both early failures. No prior report was rewritten
to pass.

Reproduction: [implementation recipe](../plans/qt_e17_implementation.md).
Next: review/merge the independent feature PR; keep E18/QML, E19/Quick, GPU backend
and full licensing/redistribution work separate. No upstream main merge authorized
by this record.
