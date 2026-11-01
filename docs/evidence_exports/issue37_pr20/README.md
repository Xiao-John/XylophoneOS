# PR20 evidence path conversion

These files document a path-sanitized derivative of the original PR20 evidence
in Git commit `da1a47c0b8455be82ba90aaf5bea393066839ac4`. Original outcomes,
input hashes and failures belong to that source, not to a new qualification.

The ledger binds the original and exported bytes, including gzip recompression,
and both existing report indexes. Personal host roots and recognized QEMU host
command tokens are replaced by configurable placeholders. Historical guest
data is not globally rewritten. Run `python3 scripts/verify_pr20_evidence.py`
to compare the original Git objects, derived files and both legacy indexes.
Other embedded historical input hashes continue to describe the original run.
Git history, remote copies and cross-machine replay are outside this conversion.
