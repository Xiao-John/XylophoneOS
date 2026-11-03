> **Evidence version:** This checkout is a path-sanitized derivative of the
> frozen source evidence, not byte-identical original logs or receipts. The
> original index and original/export hashes are recorded in
> [the Issue 37 provenance record](../../evidence_exports/issue37/qt_e15_lineage.json).
> Historical input hashes in the qualification still refer to the original run;
> configure the named template roots and matching inputs before any reproduction.

# E15 QtCore 6.8.3 scoped qualification

The implementation and guest evidence are indexed by [qualification.json](qualification.json)
and explained in [work log 0064](../../work_log/0064_qt_e15_qualification.md).
G01/G03 are scoped functional PASS for the declared single-core static QtCore
profile, with sampled rather than absolute peak memory. Redistribution and
full license-member review are NOT_RUN. Each guest report binds the actual image,
ELF and QEMU command; compressed serial logs preserve raw bytes. The system and
threading SDK manifests, Qt features, fixture receipts, G02 and regression
reports are retained alongside this index. `dash_serial_logs.tar.gz` contains
raw per-case serial logs. `PACKAGE_SHA256SUMS` hashes these evidence files.

`sha3_attribution.json.txt` preserves Qt’s upstream attribution bytes; that upstream file is not strict JSON. Component and redistribution review remain open.
