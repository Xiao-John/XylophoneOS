# 0112 Aurora C30 Rename and Review Fixes (Host-Side Follow-Up Checks)

2026-10-30. Following C30 (xos_plan v1.5), renamed five project-owned class names from
PR #29 to the required snake_case form (commit a3ae0f0, 14 files) and fixed six of the
eight actionable non-blocking review comments (1, 2, 3, 4, 5, and 8; 6 was an integration-
time conflict, and 7 was resolved by the C30 rename). Frozen evidence and historical
work logs were neither rewritten nor rebound.

Supplemental qualification is in [aurora_c30_rename_20261030](../reports/aurora_c30_rename_20261030/README.md).
Token-boundary normalization confirms the rename was a pure identifier substitution
(14/14 files reproducible byte-for-byte). Host compile checks passed 10/10; the SSG
differential fixture passed 13/13 in a real run, including the new
`stale_generation_since_resets` case. Scope audit, mock semantic probes, documentation/ABI
consistency, and whitespace checks all passed. Fixes 3 (nanosecond precision for `now_ns`
and a process-local reference point) and 4 (custom button text colors) change behavior.
The guest QEMU suite could not be rerun on this host because the Qt target build tree and
SDK image are on the author's machine. Follow-up qualification is recorded as NOT_RUN;
it is not claimed as passed.
