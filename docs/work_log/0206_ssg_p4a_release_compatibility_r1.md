# 0206 — P4A-R1 official release compatibility recheck

2026-11-05 · PR #76 head `a7c7db01f2b61e7828876841b34c30087d4d09d9` · base
`59ac60db7f68fa0f9b13b56025df8549f1a72c5e`.

## Baseline and release integrity

Fetched upstream `main`, PR #76, and the `v0.0.2-1103` tag. The annotated tag
peels to `071330f3b196d357c4a823f1719793b449513b86`; the release record binds
system build `8356e45af316fc93` to source `6fe330ce`. These are distinct from
the P4A PR head.

The live GitHub Release currently exposes five attachments: images, SDK,
Qt6 static, `release_manifest.json`, and `CHECKSUMS.sha256`. All five downloads
match GitHub API size and SHA-256. The live release has no sources attachment.
Its checksum file nevertheless names a sources archive and hashes it as
`ccde1b85…`; the repository freeze receipt records `cb6dbbfe…` and
375,131,248 bytes, while `next_release.md` records a different prefix
`a103a481…`. The previously observed 375,151,685-byte archive is not available
from the current Release API or local checkout for a fresh hash. The uploaded
checksum attachment also differs from the receipt: current SHA-256
`4e1adf5d…`, receipt `e683c807…`. The release publication/asset history is
needed to distinguish later repackaging, attachment removal, and stale records;
no release or receipt was changed. A maintainer note is in the R1 report.

## Build and guest results

The official SDK includes `xos::file::client` and matching lowercase symbols
in `libxos.a`; the previous file-client header/object overlay is not needed
for that API. The complete P4A direct build still fails: the release SDK omits
the thread header/runtime profile required by P4A and its `libstdc++` headers
disable GThreads. The Qt asset’s generated headers also contain build-host
absolute paths and its generated configuration headers are not present at
those locations. The original direct failures and an isolated compatibility
build are recorded in
[`docs/reports/ssg_p4a_release_compatibility_r1_20261105/`](../reports/ssg_p4a_release_compatibility_r1_20261105/).

Using an isolated compatibility view, all nine P4A targets built from the PR
HEAD and the fresh QEMU suite used the official release ISO and the official
Qt6 static libraries. This view supplied the missing thread runtime and
generated Qt configuration/header paths; it is not an official SDK direct
build. The SDK’s original file-client header and archive members were retained.

On the official release ISO, all 15 source/delivery scenarios passed their
independent frame audit, both resynchronization runs passed, Subscriber state
passed 25 checks, and P3C contract and ordinary Console Watch regression
passed. Short stress regression passed 11/12; run 06 ended with the Browser
provider canceled during shutdown. The historical exit-race root cause remains
`UNRESOLVED`.

A final-source rebuild after the scenario matrix built all nine targets again.
Supervisor, Subscriber, Notes, and test-fixture ELF hashes matched the matrix
build. Browser ELF hashes differed with the build output path; final-build
first-subscription and premature-EOF runs passed their independent QEMU audits.

## Premature EOF correction

Review found that EOF was treated as a clean Subscriber exit even when either
prewired source had never published an initial state. The Subscriber now exits
nonzero until both source slots have an accepted initial state. A real QEMU
negative case closes the Supervisor’s event Pipe before the first source state;
it observes no event or ACK, a non-clean Subscriber exit, and a nonzero
Supervisor result. The independent verifier passes this case.

The contract remains: ACK confirms only in-memory state, lost or mismatched
delivery is not replayed, `globalAtomicSnapshot=NOT_IMPLEMENTED`, and
`EXIT_RACE_ROOT_CAUSE=UNRESOLVED`.

No release asset, tag, freeze receipt, or upstream `main` was modified.
