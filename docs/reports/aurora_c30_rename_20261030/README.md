# Aurora C30 rename and review-fix acceptance supplement

2026-10-30. Supplement for the C30 mandatory snake_case rename (commit a3ae0f0:
DesktopSurface/GlassPanel/QtScene/SceneStream/Semantics -> snake_case, 14 files)
and the six fixable non-blocking review items (this commit).

- `rename_map.json`: per-file SHA-256 before/after the rename commit.
- `delta_proof.json`: mechanical proof the rename is identifier-only
  (word-boundary old->new substitution on the pre-image reproduces the
  post-image byte-for-byte for all 14 files).
- `fixes.json`: the six review fixes; fixes 3 and 4 are behavior-affecting.
- `checks.json`: verifications run on this host (compile 10/10, ssg diff
  fixture RUN 13/13 including the new stale-generation case, scope audit,
  doc/ABI/whitespace checks) and explicit NOT_RUN list.

Binding: frozen evidence under `aurora_sdk_review_20261030/` and earlier
remains bound to its original pre-rename sources and is NOT rebound. The
identifier-only proof extends those results to the renamed code transitively.
Guest QEMU suites were not re-run on this host (author-side Qt build tree and
SDK images unavailable): re-qualification for fixes 3/4 and case 2 remains owed
and is recorded as NOT_RUN, not as a pass.