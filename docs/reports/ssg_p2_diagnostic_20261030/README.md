# SSG-P2: preliminary large-page diagnosis (incomplete)

This is a diagnostic step, not the SSG-P2 pagination implementation. The
existing P1 reports, fixtures and raw evidence have not been rewritten.
The original browser regression and instrumented version both fail at the
scroll diff assertion; neither is a passing large-page qualification.

## Reproduction

The baseline run used `341c258`'s unmodified Browser ELF, SHA-256
`548be4a1a3ef17f03a90b15687f29ceb82bfe6f72768fab08c3547cb3a1bcd09`,
the original test `tests/aurora_platform_guest.py --case browser`, the same
synthetic page and operation sequence, and the frozen image SHA-256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.
The two preceding DOM/layout and engine-hit checks passed. The three snapshots
returned 12, 15 and 17 nodes, all capped, with reported query times 60, 60
and 100 ms. Navigation yielded `SOURCE_REPLACED`; after scrolling on the
same epoch the partial baseline yielded `RESET_REQUIRED`. That reset is a
necessary guard, not a successful complete diff.

The second run used a rebuilt Browser with diagnostic counters and identical
page, image, and test sequence. All three snapshots report `TIME` as the first
triggered traversal cap, at 22/25/27 attempted visits and 13/16/18 output
nodes. The recorded traversal elapsed 40 ms each with the existing `>30 ms`
check. Maximum depth was 4 of 18; remaining total text budget was 8126/8120/8113
UTF-16 units of 8192, with no observed text node truncated; encoded nodes
were 6058/7438/8311 bytes of the 65536-byte limit. The first triggered limit
is reported in the same precedence as the existing check. These measurements
are from this instrumented run, not retroactive measurements of the frozen ELF.

Fragment/visibility samples sum to 20/0/0 ms and publication takes 20/20/60 ms.
The clock has millisecond-or-coarser granularity; per-node samples can round
down, and publication includes validation and serialization, so these values
cannot establish the fractional contribution of layout, traversal or
serialization. The synchronous query blocks its GUI callback; event-loop
latency was not measured. There is no independent document revision sampled
during the callback. No conclusion about mutation or responsiveness is claimed.
The counter and timing probes introduce some overhead and add one diagnostic
serialization after traversal; they do not change the existing limits, query
scope, or retained SceneStream version state.

The reproduction uses synthetic test content and serial logs can include that
content. Production logging and authorization are not qualified by these logs.
See the JSON observations and compressed logs for exact details.

## Outstanding

True bounded continuation, long Notes text ranges, stale cursor and authority
handling, complete multipage baseline/diff, consumer integration, broader guest
coverage, and broker work are **NOT IMPLEMENTED / NOT RUN**. Existing P1
transport is prewired and does not provide independent per-message identity or
remote revocation. The clock check is not a hard deadline on an individual node.
The uninstrumented failure cannot be conclusively attributed to the time cap
without its own instrumentation. The rebuilt candidate subsequently passed the same 17 scoped P1 guest checks;
see `p1-regression-report.json` and `p1-regression-evidence.tar.gz`. These
checks cover the original small Browser fixture, not the failing large page.

The image-source worktree's registered-material/SDK-copy audit reports seven
checks passed; it is not a full member, static Qt distribution or relinking
license review. Its image manifest still differs from the current stacked source
and two of 725 image-source manifest entries are mismatched (`tests/aurora_platform_guest.py` and `tests/fixtures/qt6/aurora_render_probe.cpp`). The stacked worktree differs or is missing 13 of those 725 entries, including the independently changed Browser and missing Desktop files. No
unrelated sources or manifests were copied or rewritten to hide the discrepancy.
GitHub did not report CI checks for the P1 fork PR when inspected.
