# Vim 9.1.0000: source and dependency inventory

Source: the Git commit pinned in `source_lock.json`; Git tree inspected, not
cross-configured or guest-tested. `src/auto/configure` SHA-256
`cf3f66e842305a749506e9479faab39162105b1c018f8142aed2145d18d3224d`;
`src/Makefile` SHA-256
`ad798d5b1ae96e686c922219bbeaf868336771f37f81285f49b21772d276b604`.

| Dependency | Pinned candidate / boundary | Qualification |
|---|---|---|
| Vim source and runtime | Git commit in source_lock, including runtime and bundled code | Source pinned; runtime packaging and individual member licenses not audited |
| Terminal capability library | XOS ncursesw 6.5: `src/ports/ncurses/source_lock.json` | Bounded XOS subset; Vim actual link path not yet established |
| C runtime | UTF-8 newlib 4.6.0.20260123, source archive SHA-256 `6ff27e3bf022666f43f7802255be680eeff722ac181b1725d21e2e8318604ee3` | Candidate builder `scripts/build_utf8_newlib.py`; not full POSIX |
| Compiler, binutils, make and SDK | Current XOS toolchain and SDK | Exact versions and tree hashes must be frozen for each build; not yet selected here |
| libvterm, xdiff | Bundled in the pinned Vim source | Feature-dependent; member license and target behavior pending |
| Lua, Perl, Python, Ruby, Tcl, MzScheme, GUI and related libraries | Configure exposes optional integrations | Versions, availability, and inclusion in the complete target feature matrix not yet decided; not declared satisfied |
| Terminal, files, process, signals and locale | XOS public interfaces | Requires source call-path audit, cross-configuration and guest probes; not claimed complete |

Upstream `LICENSE.upstream` is copied verbatim. Modified distribution and all
bundled components require review of their actual conditions and notices.
The selected old baseline does not assert current security fixes. A successful
build or narrow configuration cannot qualify the full Vim feature goal.
