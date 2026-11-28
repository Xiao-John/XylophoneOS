# P1-J: two fresh accepted R1 distribution runs

Two complete fresh runs passed from the same frozen runner commit
`dedf69415f1942bcf860b6ec7dd2e211869501e9` and exact accepted R1 inputs. Each run rebuilt the
recorded native system, relinked all 17 glibc consumer programs, ran the package
and native GNU guests plus all five substitution suites, checked source and
negative gates, and froze its own result. The final read-only comparison passed
with verifier commit `2a64ff11e0d1dcbcdaaaafd9ecccecc780ea4f47` and script SHA-256
`147abb7c2910932f9f5d1fc08bccde72ea0b3d4a74f0fd1d6b9f425e06dcb979`.

The first comparison attempt rejected the generated depth-nine run envelope
because it reused the XPK depth-eight metadata parser. That failed orchestration
record remains unchanged. The independent verifier gives only the completed
report envelope a bounded 1 MiB/depth-sixteen reader; package metadata parsing
and every producer stage remain unchanged. It also binds both complete frozen
inventories and checks every recorded file, all immutable cross-run assets and
the actual source archives. This is a corrected consumer of the original
completed runs, not a claim that guests ran from the newer verifier source.
[Comparison attempts](comparison_attempts.json) · [Verifier scope](verifier_scope.json)

| Attempt | Fresh run UUID | Started (UTC) | Finished (UTC) | Required stages | Frozen inventory |
| --- | --- | --- | --- | --- | --- |
| 5 | `f645a9f55f014156937bd263bee870de` | 2026-11-28T12:47:10.050213+00:00 | 2026-11-28T13:12:18.274219+00:00 | 14 / 14 | 20 / 430,314,234 bytes |
| 6 | `480ad403fe0f4210a6c5e8ab1975cf26` | 2026-11-28T13:12:46.372359+00:00 | 2026-11-28T13:35:26.465667+00:00 | 14 / 14 | 20 / 430,314,234 bytes |

These are different initially absent directories with separate source archives,
receiver outputs, guest media, reports and UUIDs. The two runs use the same
verified host toolchain; this is directory-isolated repetition on the same host,
not a claim about independent hardware or a new network-isolation mechanism.
Attempts 1–4 remain failed and are excluded, including the manually continued
tail of attempt 3 and the partially successful guest work of attempt 4.
[Workflow records](workflow.json) · [Comparison](comparison.json) ·
[Earlier failures](attempts.json)

## Exact scope and input identities

| Input | Identity |
| --- | --- |
| Accepted bundle | `p0-r1-glibc-release-20261128.tar`, 430,346,240 bytes; SHA-256 `492c7b311431132398b84f62ff9357f516983039094559d41d4159e3e7e19ff4` |
| Native system source | `819ea63ae84b1e89862648af002c2a09d1936c02`; all 2,211 recorded inputs matched |
| Runner source | `dedf69415f1942bcf860b6ec7dd2e211869501e9`; clean Git archives separately recorded |
| Native build | `7c8c59058be0b5f1` |
| Recorded glibc SDK | `56c596967ff6ec6c51b593e91ff01f3c4bc7ac2903ace6ab426b290b358f4703` |
| Release manifest | `0e97d5f9e563fc33619563af1b35f041e021e507fa1ef1abaabf4354731a188e` |
| Frozen rollback SDK archive | 8,917,110 bytes; SHA-256 `86583de2a13b3eea095e94e3768243fdb40216bdfb7e01bc8909d969331e5f66` |

The existing accepted first qualification and verified public delivery are an
explicit entry gate. The glibc consumer SDK, historical frozen rollback SDK and
host SDK keep their separately recorded roles. This workflow does not requalify
current-main kernels/runtimes by relabeling R1 evidence.
[Source material checks](source_materials.json) ·
[Native source binding](system_source_bindings.json.gz) ·
[Native rebuild](native_rebuild.json)

The entire producer Git tree is also available at the verified public
[source anchor](https://github.com/Xiao-John/XylophoneOS/commit/110cb65159af7b43220ed6a76d30a185dd014c77)
`110cb65159af7b43220ed6a76d30a185dd014c77`. Its tree
`241ed633b8e40c013d093dbc52f1f8b3f18e48ce` is identical to the local producer tree. The actual run
records retain their original producer commit and source-archive digests. A Git
archive from the remote commit may have different wrapper metadata; source-tree
equality is not presented as equality of those archive bytes. New repeats from
that source record their real commit and new UUIDs.
The separate read-only verifier has its own public [source anchor](https://github.com/Xiao-John/XylophoneOS/commit/9420458011f521c342a0f36c5152e8c96ad2a81a)
`9420458011f521c342a0f36c5152e8c96ad2a81a`, whose tree
`be7b30f79342b8073fe94c6283951866248dd924` matches the actual local verifier. Both tree pairs
were checked directly using Git; neither mapping rewrites an original report.
[Source-anchor mapping](source_anchor.json)

The ISO, flat kernel and ordinary hello ELF match the accepted R1 bytes. The
kernel's loadable binary, layout and symbols match too. Its rebuilt debug ELF
contains the receiver build path, so it differs from the original producer's
debug ELF; both identities are retained and that difference is explicit. The
same rebuilt debug identity is obtained in these two receivers.

## Actual target results in each run

| Group | Qualified behavior |
| --- | --- |
| Package lifecycle | 3 checks: installer/idempotent package setup and Python; cold ordinary boot and native ownership; daily/wheel reclamation with Python and user data retained |
| GNU Seed | 20 cases: tool versions; real C/C++ compilation, linking and execution; GNU Make from Xshell and Dash; undefined-symbol rejection; C/C++ and Python after cold boot |
| Receiver materials | Five isolated kits, 17 programs: xypm, dash, 13 daily tools, GNU Make and CPython; original ELF identities match R1, deliberately changed replacement ELFs are independently reproduced |
| Real substitution guests | Original and replacement applications execute using their actual receiver output; xypm reads the installed disk, dash exposes the changed PID result, daily/Make/CPython expose the changed exit member while retaining expected behavior |
| Source correspondence | 140 component-source records plus authenticated glibc archive, signature, key and SDK binding |
| Archive preflight | Fresh recipient reopen, GNU Make signature and unchanged 1,515 GNU Seed installed files; missing/duplicate/changed/extra members and incomplete Seed arguments rejected |
| Publication gates | Wrong hash, stale SDK binding and missing source rejected before a frozen output exists |

The existing guest reports keep their exact `passed_subset` scope. The outer
workflow `passed` means every required named subset completed, not that every
possible OS capability was tested.
[Package report](guest_packages.json) · [GNU report](guest_gnu.json.gz) ·
[Receiver relinks](receiver_relinks.json) · [Substitution guests](guest_relinks.json) ·
[Preflight](receiver_preflight.json) · [Negative gates](negative_gates.json)

## Frozen files and evidence retention

Both frozen directories were checked for exactly their recorded filenames and
for every file's complete size and SHA-256, beyond simply finding the listed
files. 20 frozen files have identical bytes across the two runs;
the comparator requires all 15 immutable distribution assets to match and
verifies the other five report/receipt/checksum files independently. This pair
also produced identical bytes for those five files. Per-run observations and
outer workflow timestamps remain separately recorded; equality is checked, not
assumed.
[Frozen inventories](frozen_inventory.json)

The peak-space fix retires each temporary guest disk only after its last real
consumer has closed, after checking its complete hash and recording the
producer/consumer report identities. GNU media is retired after the combined
guest, package media after preflight readback, and the installer snapshot after
all substitution suites. The final freeze requires all three receipts and
unchanged report bytes.
[Media lifecycle receipts](guest_disk_retirement.json)

After each passed run, all frozen assets, raw reports/logs/receipts, source
archives, actual receiver results and native build outputs were retained and
verified. Complete original inventories were rechecked before removing the
reproducible temporary expansion. The two compiler-driver symbolic links were
preserved as exact link strings without dereferencing an external tool path;
other special files were rejected. Raw report paths and statuses were not
rewritten. After both runs had fully passed, identical immutable regular files
in the retained copies could share same-filesystem hardlinks only after matching
the independently generated bytes, size and mode. The receipt records this
physical storage reuse and any filesystem timestamp difference; no execution
stage reused a previous run output. Relocation is a separate byte-conservation
record.
[Retention inventories](byte_conservation.json.gz)

The public JSON/logs here are explicit derived exports with host paths abstracted.
Original hashes name unpublished raw records and artifacts. Only
[manifest.json](manifest.json) hashes public sibling leaves. The exported GNU
serial logs retain actual guest compiler temporary paths; those are guest
observations, not host filesystem disclosures.
The GNU JSON command fields use `XOS_GUEST_SOURCE` and `XOS_GUEST_OUTPUT`
placeholders with an explicit guest-path expansion map. Export checked that
expanding each template reproduces its original command exactly. Actual guest
outputs and serial observations retain their guest paths. The preliminary export
also exposed host runtime and per-receiver temporary directory prefixes; those
prefixes were abstracted before the final staged scan. Original records were
preserved throughout this review.
[Export origins](publication.json)

## Validation and limitations

The final host suite passed 21 tests, including the actual depth-nine report
shape, seven malformed-envelope subcases, extra frozen files, inconsistent
inputs and changed immutable artifacts. The original producer lifecycle suite
had already passed its 15 tests before the two guest runs. An exact source view of
the accepted native commit passed the registered licensing audit: 10 materials,
zero active open items, and the existing deferred/not-applicable boundaries
preserved. Its 2,547 audit-source files were checked against that exact Git
revision; this is separate from the 2,211 native compilation inputs and from the
current runner's source. The final documentation, evidence and publication path
gates, including inherited global-report failures, are recorded in
[validation.json](validation.json).
[License audit](license_audit.json) · [Audit source](license_source_binding.json.gz)

This is the accepted R1 receiver/source/relink/guest/freeze automation. It does
not repeat full glibc/GCC/all-upstream source compilation, arbitrary power-loss
injection, physical hardware qualification, a new installed dynamic DHCP/TLS
combination, or a new public release upload. The earlier upgrade-fault and
frozen-SDK round-trip campaigns retain their first-R1 evidence; they are not
claimed as fresh J guest tests. The first qualification and its required
delivery gates remain independent prerequisites.

Reproduction commands and lifecycle rules are in the
[contract](../../contracts/repeated_distribution.md). The
[work log](../../work_log/245de5c3_p1_j_distribution_repetition.md) records the
source commits, failures and delivery boundaries.
