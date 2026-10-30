# Midnight Dock native glyph refinement

Six original, small vector glyphs add recognisable Home, Apps, Studio, Settings,
Quality and Hide cues alongside their existing text. They use the current native
text token and refresh when appearance settings change; no timer, font or image
dependency is added. The text, keyboard access and single-Surface session remain.
This requires the separately reviewed standard-button icon fix in fork PR #4;
the original SDK style alone does not draw these icons.

The real QEMU 800×600 scanouts are [before](midnight-before.png),
[after](midnight-after.png) and [Daybreak high contrast](daybreak-high-contrast.png).
The host pixel comparison detects a change in all six fixed Dock button regions;
it is not a semantic or aesthetic-quality score. Final aesthetic acceptance is
still a human decision. The unchanged system image SHA-256 is
`165686bb0de0b0b2f33645ede2cf10c2badb25ea363f3ef57ed74641503b0b08`.

On the local Desktop + SDK + SSG fix combination, the modified desktop passed
interactive, lifecycle and sequential session gates; Studio and dash passed on
rerun: **5 suites / 30 top-level checks**. One first Studio attempt passed its
own control/edit checks but the unchanged legacy Qt ELF printed `QT_WIDGETS_OK`
without returning before the wait timeout. That failure and its raw serial log
are retained; the same binary later exited normally and the gate passed. Its
initial cause is **unknown**, and the successful rerun does not eliminate an
intermittent lifecycle risk.

`manifest.json` records each run, commands and source/image/ELF hashes. The
verified evidence bundle retains all raw PPMs, serial logs, reports, build
receipts, comparison and failure; SHA-256 values are recorded for every member.
This does not implement multiwindow composition, cross-process theme negotiation,
real-time refraction, broader resolution coverage or a performance improvement.
