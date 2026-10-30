# 0111 — Midnight Dock refinement

2026-10-30. Independent Desktop follow-up at `b1b56225`. Six text navigation
buttons gain theme-colored, native vector glyphs, rebuilt only when settings
change. Existing labels, focus, single-Surface ownership and session handoff
remain. This depends on fork PR #4's standard Qt button icon rendering fix.
No kernel, public ABI, QPA, driver, foreign assets or new dependencies change.

Built the real target with `src/ports/qt6/build_widgets_fixture.py` against the
E17 Qt/SDK and ran the existing Desktop and dash guest harnesses on a local
combination of the three reviewed units and fixes. Five suites / 30 top-level
checks passed after rerun; a host pixel check found changes in all six Dock
regions of real QEMU scanout. Commands, hashes, before/after screenshots, raw
logs and retained failure are in [the report](../reports/aurora_midnight_dock_20261030/README.md).

The first Studio run's legacy Qt application printed its success marker but did
not return before the wait timeout. A same-binary rerun passed; root cause is
unknown and remains an intermittent risk. This change does not establish a
compositor, a global theme service, full accessibility, physical hardware,
larger displays or final aesthetic approval. After dependency review and any
upstream base change, rebuild and repeat the affected Desktop gates.
