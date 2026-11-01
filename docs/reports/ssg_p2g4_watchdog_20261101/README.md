> Historical archives and indexes for this report are retained under `docs/evidence_exports/issue37_pr49_review/original/ssg_p2g4_watchdog_20261101/`; the current flat manifest covers the derivative.

# Browser pagination: watchdog synchronization

The branch now uses the existing native-join watchdog implementation from
commit `c9ff0bce050a6777b5f1777c714f9443a23e3ee4`, already present in later
SSG branches. All four P1 programs and the separate test-only Oracle Browser
were rebuilt. On one fixed document, the real guest produced two complete
34-page / 267-node snapshots, matched the independent structure Oracle and
passed the independent A/B reconstruction and a real PS/2 link click.
The guest serial record is `pagination-guest.serial.log.gz`.

The first local capture attempt stopped before guest execution because the
strict receipt serializer lacked explicit workspace and toolchain mappings.
The rerun supplied those mappings; the serializer was not weakened. This is
`PASSED_SCOPED` for A1 structure/text on the fixed fixture, not overall Gate A,
Gate B/C, arbitrary pages, WebKit, or a proof that all exit races are fixed.
