# E15 supplemental guest recheck

[summary.json](summary.json) indexes the unchanged production inputs and new
lifecycle fixture. [recheck.json](recheck.json) records 16 real guest cases,
commands, runner exit codes and image/ELF hashes. Per-case JSON and compressed
raw serial logs preserve guest outcomes and resource counters. The lifecycle
build receipt binds its exact source and dependencies. `audit.json` records
tool/package hashes, the Core build check and source replay comparison.

Fresh G02, threading and file/persistence regressions have separate reports and
raw serial logs. `run_regressions.py` preserves the actual private-overlay
invocation; its existing artifact stage is required. The primary reusable entry
is `tests/qt6_qualification_recheck.py`, documented in
[0065](../../work_log/0065_qt_e15_lifecycle_recheck.md). Previous evidence remains
in its original directory. Distribution and full member-license audit are not
qualified. `PACKAGE_SHA256SUMS` covers this supplemental evidence package.
