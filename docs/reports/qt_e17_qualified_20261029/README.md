# E17 / Aurora restricted guest qualification

Entry point: [qualification.json](qualification.json), [implementation and scope](../../work_log/0078_qt_e17_aurora_qualification.md).

`review_gates/`: real Widgets/editor/Aurora and current-profile G04; all twelve suites passed.
`review_g02/`: 19 G02 checks. `review_core_regressions/`: 12 fresh-current-SDK QtCore suites.
`review_system_regressions/`: 15/10/10 thread groups and 8/4 file/persistence groups.
`review_memory_compare_2/`: three matched scenes in the same ELF, sampled memory only.
`block_faults/`: actual QEMU block write/flush EIO after ELF load and staging; old file
bytes survive offline comparison and clean reboot. Same-boot file read/sync remains
failed after these storage errors: serial rescue works, reboot is required. This
is not physical-media, power-loss or arbitrary transaction qualification.
`host_recovery/` is explicitly host/FatFs fault evidence, not guest hardware evidence.

PNG and JSON remain directly readable. Raw serial, framebuffer bytes and PPM images
are compressed losslessly as `.gz`. Build logs, SDK/system manifests, Qt prepared
source hashes and receipts are preserved. The actual large libraries/ELFs and
private system image remain under the receipt paths in the task's local worktree;
no binary Release was published.

`attempts/` retains failed compilation, premature/mis-scripted probe, stale receipt,
palette review, host-export and incorrect thread-count assumptions, plus block
faults armed too early during mount. Reports are not rewritten to manufacture passes.
The final first-class report uses the corrected/frozen inputs. Zero timing differences
mean below the 10ms clock granularity; sampled user pages are not an absolute peak.
