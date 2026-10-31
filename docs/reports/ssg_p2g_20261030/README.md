# P2G partial: Consumer pagination continuity

**Gate B NOT_QUALIFIED.** This delivery is a partial implementation, not a new guest acceptance run. B1 and B3 new complete A/B baselines, B2 real scroll, B4 independent Consumer Diff, B5 changed-content control, all requested guest fault cases, resource recovery and affected guest regressions remain NOT_RUN or NOT_IMPLEMENTED. There are no new A/B frames, screenshots, reference comparisons, or scroll evidence here. P2F A1 remains limited to its two fixed inputs; overall Gate A is still NOT_QUALIFIED. The pre-existing nonpaged first TIME truncation remains unresolved.

## Change and boundary

The existing `browser-pages` Consumer now checks source instance, epoch, revision, page sequence, constant integer `scrollY`, unique nonempty continuation cursors, and an empty final cursor. Invalid responses cannot lead this code path to its complete marker. It continues to report `completeness=ORACLE_REQUIRED`: these checks do not detect a missing whole subtree and do not publish a trusted baseline. Source and revision are not cryptographic integrity protection; without an explicit per-session identity on every response, hostile or arbitrarily corrupted same-source/same-revision pages cannot always be distinguished. Sequential request framing and the Provider's one-live-session rule do not establish arbitrary fault immunity. No Diff was implemented; paths alone cannot reliably identify moved or reordered identical siblings.

## Evidence and reproduction

* `consumer-build.log`: cross build of the modified Consumer succeeded using the existing E17 SDK and Qt Widgets target. `build-sha256.txt` records its local ELF hash and relevant source hashes. The ELF is not checked in. Build warnings remain in the log. The build receipt is not a guest test.
* `continuity-test.log`: compile and run `clang++ -std=c++17 -Wall -Wextra -Werror tests/fixtures/ssg_p2g/page_continuity.cpp -o ${XOS_TEMP}/be968d3b3d93b062 && ${XOS_TEMP}/c9f714d29bd29953 It checks the real shared continuity class on the host, including source/revision/sequence/scroll drift, repeated cursor, invalid termination, and post-completion rejection. It is not a guest transport test.
* `structure-validator-test.log`: `python3 tests/ssg_browser_structure_test.py`, 52 host verifier tests passed. These test the existing P2F verifier, not the new Consumer on a guest.
* `environment.txt`: no QEMU on PATH. Existing P2F build evidence documents a different Linux environment; it explicitly excludes QEMU, ELF and disk images. E17 SDK/Qt was available locally and reused for the cross build. No new QEMU interaction is claimed.

## Remaining engineering work

Implement bounded Consumer-owned complete baseline storage with atomic publication, a documented stable matching/ambiguity policy for structural changes, and a Diff over fields actually present in this protocol. Capture independent reference and actual Consumer results for both the same-document scroll and explicitly cross-document content control. Test scroll and reload during pagination, stale requests, frame corruption and loss, process exit, resource/TIME limits, duplicate IDs, parent/order faults and repeat snapshots on a real guest. A reliable same-revision mixed-session rejection may require an explicit protocol session discriminator repeated on every page; analyze private protocol compatibility before changing it. Record raw evidence and recovery counters, and rerun affected guest regressions. Do not claim Gate B until all required checks pass.
