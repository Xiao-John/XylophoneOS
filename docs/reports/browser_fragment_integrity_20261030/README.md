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

Raw serial, actual QEMU commands, source/ELF/image hashes, SDK build receipts,
JSON snapshots and guest scanout are preserved here. These runs do not establish
cross-process observation, arbitrary CSS clipping, modern Web support or
compositor occlusion. Further affected functional/lifecycle gates on the combined
source are recorded separately, not inherited from the old 15-suite report.
