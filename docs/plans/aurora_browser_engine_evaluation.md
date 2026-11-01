# Browser B0 engine evaluation and executable next steps

2026-10-29. Compare actual port surfaces, then freeze a tractable local prototype.
This document records engineering choices rather than claiming modern website
compatibility. Selected source and actual archive/member hashes are in
`src/ports/aurora_browser/source_lock.json`.

| Area | liteHTML0.9 (selected) | NetSurf (investigated, not ported) | Qt rich text (considered) |
|---|---|---|---|
| HTML origin | bundled Google Gumbo C99; engine C++/STL | official project separates Hubbub HTML5,LibDOM,LibCSS,LibParserUtils,LibWapcaplet | QtBase QTextDocument rich-text subset |
| CSS/layout | actual block/inline/flex code crosscompiled; callback painting | fuller browser architecture plus several separately built libraries; XOS build untested | narrower rich-text formatting, insufficient independent layout-engine goal |
| Text/images | target QFontMetrics/QPainter, embedded DejaVu and bounded BMP callback | needs new frontend/plotter/font/image/resource integration | available Qt raster path, but not selected as Web engine |
| Links/scroll | engine mouse hit testing plus one Qt viewport and scrollbar | browser frontend/lifecycle must be ported | built-in rich-text navigation possible but does not answer required engine evaluation |
| JavaScript | none in selected engine; UI explicitly off | JavaScript/backend/license details not completely reviewed; no claim of equivalence | no JavaScript engine |
| Toolchain/libc | actual XOS C++17 and C99 compile/link passed without new stubs | GCC/Clang officially recommended; actual XOS calls, stack and dependency closure NOT_RUN | already Qt-linked but not independent HTML5/CSS engine |
| Thread budget | no new engine threads; reuses Qt/QPA | XOS thread/stack/memory budget NOT_MEASURED | reuses Qt |
| License | upstream BSD-3-Clause; bundled Gumbo Apache-2.0; unchanged upstream archive and original texts retained | per-component/static-link/source requirements need separate full review; not guessed from project name | existing Qt static-distribution obligations remain |
| Scope/security | bounded local subset + guest negative inputs; not arbitrary-Web safety qualification | unreviewed XOS port, no target acceptance | not tested as browser |

Primary sources consulted: [liteHTML repository/readme](https://github.com/litehtml/litehtml),
[exact v0.9 source](https://github.com/litehtml/litehtml/tree/6ca1ab0419e770e6d35a1ef690238773a1dafcee),
[NetSurf project dependency descriptions](https://www.netsurf-browser.org/projects/),
[official portability/build guidance](https://www.netsurf-browser.org/developers/).
The NetSurf source web viewer and about page were unavailable to the research
reader; detailed runtime/JavaScript/license claims remain unreviewed. The larger
integration surface is our inference from the official dependency split, not a
measured failure of NetSurf on XOS. No NetSurf source or binaries are shipped.

The chosen source is tag v0.9, commit
`6ca1ab0419e770e6d35a1ef690238773a1dafcee`. This is a deliberately pinned,
self-contained source snapshot for this prototype, not a claim to be the newest
or a security-maintained release. `git archive` preserved the entire exact upstream
tree (including Gumbo original LICENSE); the archive is not mislabelled an official
release tarball. XOS patches to the upstream code: none. integration/admission
code is Apache-2.0; each upstream file is verified before cross compilation.
The initial official-host codeload retrieval failed TLS; the successful Git fetch
and exact Git archive supply the actual source provenance instead.

B0 evidence requires target static library + linked ELF, not a host demo. B1 then
requires guest local pages/input/pixels/errors/reclamation; its exact scope is
[the application contract](../contracts/aurora_browser.md). All final build and
acceptance commands are persisted with artifact hashes in the report.

Next executable work: qualify the network device mechanism through a separately
merged ABI claim; put lwIP policy and connection/session identity in a user service;
then supply the already bounded HTTP parser with real service bytes and connect a
provider to the container. Verify partial sends/reads, close/timeout/peer death,
relative URLs/resources and redirect bounds against a user-controlled host HTTP
service before B2 passes. Independently audit renderer admission and fuzz malformed
HTML/CSS/images before broader untrusted content. HTTPS needs a reviewed TLS port,
real CA store, domain/chain/time checks, trusted time and entropy. JavaScript needs
its own process/runtime/resource and event integration evaluation. Chromium or
Firefox remain a separate toolchain/libc/VM/thread/dependency project.
