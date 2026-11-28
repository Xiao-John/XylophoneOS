# P0 public delivery evidence — 2026-11-28

The SDK recovery workflow completed successfully and published the unchanged
five SDK assets. The original artifact source is `8b2dee22`; the recovery
validation commit is `b60b9aea`. The original qualification remains unchanged.
The separately bound R1 tar and checksum were then uploaded, publicly downloaded
without authentication and verified against the saved version and inner manifests.

- `sdk_publication.json`: completed workflow, public release/tag observation and
  fresh C/C++ consumer results. Its five-asset observation precedes any later R1
  attachments; it does not redefine the SDK checksum set.
- `sdk_recovery_qualification.json`: the real token-free consumer proof extracted
  from completed job 140885101481. Build-time `guest_qualification: not_run` is
  historical metadata; the report status and application results are the actual
  fresh consumer qualification.
- `sdk_public_download.json`: independent hashes of all five publicly downloaded
  files, checked against the server and four `SHA256SUMS` entries.
- `r1_sdk_consumer.json`: independent extraction of the public host SDK, followed
  by the documented R1 C++ build/check/pack. The resulting XPK passes its own
  R1 profile and is rejected by the host default profile. This generated app
  was not run in a guest; R1 guest qualification remains in its frozen reports.

- `r1_public_download.json`: both actual public downloads, outer size/digest,
  22 bundle entries, 19 frozen checksum entries and 20 frozen manifest files.
- `release_assets.json`: final seven uploaded assets, preservation of the
  original SDK five, original tag, prerelease flag and unchanged stable Latest.

The [final delivery receipt](../../releases/p0_glibc_preview_3_delivery.json)
records the verified SDK/R1 public-delivery gate and their separate profiles. No raw operator logs or credentials
are included here. The flat evidence index binds these exact exported files.
