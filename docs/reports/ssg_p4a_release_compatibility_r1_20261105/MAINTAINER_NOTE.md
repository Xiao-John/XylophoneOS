# Release metadata discrepancy — maintainer review requested

The current GitHub Release API returns five attachments and no sources archive.
Its 793-byte `CHECKSUMS.sha256` was updated at `2026-11-04T15:56:26Z`, after the
release publication at `14:59:27Z`, and currently hashes to
`4e1adf5d8e3ce3c877f41708a2257c29ce434e211c416647de014aeac06b0cd7`. The frozen
receipt records `e683c807b53bc462eed3f8c2316e1e6be139551ec334cbc97ee1138f8d3f30d2`
for the same filename and size.

The uploaded checksum contents name
`sources/xos-0.0.2-1103-sources.tar.gz` with SHA-256
`ccde1b85e391cc7f1cadaca8a661ae89213658184044ae94cbf465e50f23129e`. The
repository receipt records a different archive SHA-256
`cb6dbbfe20d73657fa4e0c5c082903b654a7d76be7b8ef0d54049851878bbd60` and
375,131,248 bytes. `next_release.md` records another SHA prefix (`a103a481…`)
and 357.7 MB; an earlier observation supplied 375,151,685 bytes. There is no
current GitHub attachment from which to independently recompute the archive
hash or exact size.

Please check the upload/re-upload/deletion history and identify the
authoritative sources archive. Then restore the matching attachment or
reconcile the checksum and frozen receipt under the release-maintenance
process. This task changed none of them.
