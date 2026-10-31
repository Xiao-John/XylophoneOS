# C6 repayment: guest re-qualification of the B1 C30 rename

2026-10-31. Clears `docs/tech_debt.md` item **C6** (the guest NOT_RUN debt left by
PR #39's rename acceptance) on this host, and clears the 0145 NOT_RUN items for
`qxos.moc` regeneration.

## Result

| suite (QEMU guest, branch image) | result |
|---|---|
| `aurora_standard_button_guest` (standard.elf) | **PASSED 3/3** |
| `aurora_platform_guest --case render` (render.elf) | **PASSED 13/13**, 11 screendumps |
| `aurora_platform_guest --case semantic` (semantics.elf) | **PASSED 5/5** |
| `ssg_diff_guest --expected-checks 13` (ssg_diff.elf) | **PASSED 13/13** incl. `stale_generation_since_resets` |
| host `aurora_blur_cases` | **PASS**, 396 vectors + 6 rejections |

All four fixture ELFs were built from the renamed tree (`ac8160d` + `c938bf6` +
the `::fonts` fix in this PR) with the real host moc 6.8.3 regenerating
`qxos.moc`; each suite ran immediately after its fixture build so receipt input
hashes match. Full per-suite reports and logs: `evidence/`.

## Pipeline (reproducible; exact commands in `checks.json` and fixture receipts)

verified private QtBase (prepare_gui_source, patches 0001–0010) → host Qt 6.8.3
tools → targeted seven-library target build (the qualified E17 configuration
builds libs only, not plugin dirs) → fresh version-matched threading SDK →
fixtures → guest suites on a branch-built `build/xos.img`.

## Carried fixes (committed with this report)

- `patches/0009-xos-freetype-no-mmap.patch` — bundled freetype's unix
  `ftsystem.c` required `sys/mman.h`, which XOS newlib does not provide; the
  patch takes the file stream's existing alloc+read fallback. Without it the
  current tree cannot build target Qt at all (latent breakage found by this work).
- `patches/0010-xos-host-arm64-acle.patch` — Apple clang ≥ 21 arm64 declares
  `__yield` only via `<arm_acle.h>`; host-build-only guarded include.
- `qxos.cpp`: `mutable ::fonts fonts;` — target g++ `-Wchanges-meaning` rejected
  the post-rename unqualified member declaration (host clang did not).
- `tests/ssg_diff_guest.py`: `--expected-checks` default 12 → 13 (harness was
  still counting pre-#29 checks; the suite failed on count, not behavior).

## Binding

Frozen pre-rename evidence stays bound to its original sources and is not
rebound; this report is the fresh guest re-qualification on the renamed
baseline itself.
