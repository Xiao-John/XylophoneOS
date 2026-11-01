# Upstream synchronization of Aurora Desktop draft

The branch merged the synchronized SSG consumer branch `59b14da7f2b466a663fdabe86f7467f799c2fd40`, which includes upstream main `8ec04891f18d2c7bfa8629f25e2d1fd39233712f`. The Desktop source was adapted to the upstream snake_case `desktop_surface` and `glass_panel` APIs.

The Desktop, Studio, semantics, render, session and compositor-gap programs cross-compiled. With the reused read-only guest image and the separately rebuilt Notes/Browser from the synchronized dependency, the Desktop interactive case passed 10 checks and the Notes/Browser/Studio handoff case passed 5 checks. Guest image SHA-256: `972f3a67012576022b67525da90c654a23b273b82cc0f1619fb6c529805ccd41`; Desktop ELF SHA-256: `bee6fa47e2657d1f0da63c7fe8fe396ecd0ff4c76b2a98cc4371e4d16dc67d74`. These are scoped tests of the recorded combination, not a multiwindow or physical-hardware qualification.

Thirty-nine existing report/log files exposed host-specific paths. Sanitized current-tree versions and raw/exported hashes are included; original bytes remain local. Existing Git history may still contain original paths. This synchronization does not claim historical erasure, production SSG authority or SDK distribution qualification.
