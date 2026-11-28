# P0 public delivery evidence — 2026-11-28

The SDK recovery workflow completed successfully and published the unchanged
five SDK assets. The original artifact source is `8b2dee22`; the recovery
validation commit is `b60b9aea`. The original qualification remains unchanged.

- `sdk_publication.json`: completed workflow, public release/tag observation and
  fresh C/C++ consumer results. Its five-asset observation precedes any later R1
  attachments; it does not redefine the SDK checksum set.
- `sdk_recovery_qualification.json`: the real token-free consumer proof extracted
  from completed job 140885101481. Build-time `guest_qualification: not_run` is
  historical metadata; the report status and application results are the actual
  fresh consumer qualification.
- `sdk_public_download.json`: independent hashes of all five publicly downloaded
  files, checked against the server and four `SHA256SUMS` entries.

The [final delivery receipt](../../releases/p0_glibc_preview_3_delivery.json)
tracks overall SDK/R1 publication separately. No raw operator logs or credentials
are included here. The flat evidence index binds these exact exported files.
