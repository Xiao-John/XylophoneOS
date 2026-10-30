# 0106 — Aurora standard controls review fix

2026-10-30. Independent SDK follow-up at `758dde49`. Aurora continues to paint
the panel, delegates standard button label/icon layout to Qt and respects an
explicit widget palette, including line-edit fill. No system ABI, kernel, driver
or QPA change. The E17 Qt 6.8.3 SDK was used with
`src/ports/qt6/build_widgets_fixture.py`; `tests/aurora_standard_button_guest.py`
ran on the frozen one-core/512 MiB QEMU image.

The same three checks failed on the old SDK and pass on the final build; actual
scanout, full commands, SHA-256 receipts and resource counts are in
[the report](../reports/aurora_standard_button_20261030/README.md). An initial
repair passed two state tests while the screenshot still exposed a dark field;
that incomplete result is retained and the final test checks painted pixels.

This does not qualify every Qt widget, accessibility tool, disabled state or
third-party application. Existing E17 `Canvas/Panel/Button` have separate
hard-coded visual/motion behavior and do not yet uniformly consume the v2
preferences. Actual combined UI/Notes/Browser regressions are separate; see
subsequent integration evidence. Review before changing the upstream SDK branch.

The final three-check control fixture also ran under xsh and actual dash with
normal GUI exit and resource recovery; see [dual-shell evidence](../reports/aurora_standard_button_dash_20261030/README.md).
