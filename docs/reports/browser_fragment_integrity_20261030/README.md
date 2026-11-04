> **Evidence version:** This checkout contains a path-sanitized derivative of
> the original evidence, not byte-identical raw logs or reports. The
> current index hashes the files in this checkout. The original index and
> its source commit are preserved and identified in the
> [PR 44 provenance record](../../evidence_exports/issue37_pr44/original-pr44-lineage.json).

# Browser SSG fragment and query-scope regression

The browser now clips each bounded real engine fragment individually before
deriving visibility. The union rectangle remains a bounding box and may contain
holes. A truncated fragment list produces explicit uncertainty rather than an
assertion of full visibility or offscreen status. This is still viewport
visibility within the admitted liteHTML subset; external occlusion is unknown.
`queryScope` separates stable query selection from scroll/viewport metadata and
requires the separately reviewed SDK diff repair in fork PR #3.

Real one-core/512 MiB QEMU runs used system image SHA-256
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08` and a
local combination of `b1b56225` plus code changes `8120215`, `3995120` and
`0a40448`:

- `geometry`: 6/6 target-side tests, including two disjoint offscreen fragments
  whose union spans the viewport, clipping and truncated-fragment cases.
- `browser`: 7/7 top-level checks using the real liteHTML document and layout,
  hidden/offscreen text, actual link hit, scroll metadata and reload epoch. It
  also checks that every reported visible fragment is an actual clipped fragment.

Serial output, path-sanitized QEMU command records, source/ELF/image hashes, SDK build receipts,
JSON snapshots and guest scanout are preserved here. These runs do not establish
cross-process observation, arbitrary CSS clipping, modern Web support or
compositor occlusion. Further affected functional/lifecycle gates on the combined
source are recorded separately, not inherited from the old 15-suite report.

Round 2 rebuilt the system and Browser with main `48882c9` and the updated
#40 layer. The first guest attempt reached 2/7 before the old runner rejected
the SDK's required reset for a capped snapshot. The same ELF and image passed
7/7 with the contract-aware runner, including independently checked clipping,
stable scroll scope, reset without inferred removals, reload and resource return.
[Both outcomes](round2_guest.json) are tied to their image and ELF hashes.
The historical 6/6 geometry fixture was not rerun.
