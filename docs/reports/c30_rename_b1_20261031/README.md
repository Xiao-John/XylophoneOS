# C30 rename batch B1 acceptance (15 self-authored classes)

2026-10-31. Payment of `docs/tech_debt.md` item **B1**: the15 remaining
self-authored CamelCase class names on main renamed to snake_case under C30.

- rename commit `ac8160d`: identifier-only rename across 20 files, 117 old
  identifier occurrences, zero residual old identifiers in scope.
- fixes commit `c938bf6`: post-rename collision resolutions (32 changed lines),
  qualifications only -- no further renames.

## Files

- `rename_map.json`: the15 old->new names, scope and exclusions, per-file old
  identifier counts and per-revision SHA-256 (pre `c47b355`, rename
  `ac8160d`, fixes `c938bf6`).
- `delta_proof.json`: mechanical identifier-only proof -- word-boundary
  substitution applied to the pre-image reproduces the rename commit
  byte-for-byte for all 20 files (`all_files_identifier_only: true`); the
  recorded exception is `theme.cpp`, where upstream `QPalette::Window` /
  `QPalette::Button` enums were kept verbatim.
- `fixes.json`: every post-rename fix line with its reason -- injected-class-
  name collisions (member `pointer`/`canvas` vs same-named classes; upstream
  inherited `QPlatformWindow::window()` inside renamed class `window`;
  base member `window()` hiding the namespace class inside `backing_store`).
- `checks.json`: commands actually run on this host and the explicit
  NOT_RUN list.

## Renamed classes

`BackingStore` `Brand` `Button` `Canvas` `Editor` `Fonts` `GuiDispatcher`
`Integration` `NoteHighlight` `Panel` `Pointer` `Screen` `Style` `Window`
`XosWakeGate` -> snake_case equivalents (see `rename_map.json`).

Not renamed: `QEventDispatcherXos` and `QXosIntegrationPlugin` -- upstream
QPA-interface-forced names under C30's exemption (tech_debt item B2, awaiting
user adjudication).

## Binding

Frozen evidence under `aurora_sdk_review_20261030/`,
`qt_e16_qualified_20261028/`, `qt_e17*` and earlier remains bound to its
original pre-rename sources and is NOT rebound. The identifier-only proof
(`delta_proof.json`) extends those results to the renamed code transitively,
the same rule as `aurora_c30_rename_20261030`. Guest QEMU suites were not
re-run on this host (target Qt build tree and SDK images are author-host
only): they are recorded as NOT_RUN, not as passes.

## Verification headline

host syntax 14/14, ssg_diff_integrity RUN 13/13, mock agent 3/3 probes,
docs_consistency passed (543/66/73), abi_doc_consistency PASS,
`git diff --check` clean; scope audit with fork-point base shows
`kernel_source_changes: []` and a single flagged file -- the QPA rename file
itself (see checks.json CONTEXT).
