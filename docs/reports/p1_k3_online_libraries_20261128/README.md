# P1-K3: explicit online GNU library qualification

The exact native system `94674a7e28151485` passed **16 actual guest cases
across seven cold boots**. Every case restored its own boot's exact free-page,
task and completion baseline. This is the named, opt-in GNU C online profile
with the separately built matching native unwinder and real GNU pthreads.

| Boot | Case | Wall seconds | Result |
|---|---|---:|---|
| online | dependencies | 7.6 | passed |
| online | namespaces | 10.234 | passed |
| online | tls | 11.233 | passed |
| online | lazy_tls | 8.093 | passed |
| online | pthread_exit | 7.073 | passed |
| online | last_worker | 12.296 | passed |
| online | concurrent | 8.801 | passed |
| online | pin_replacement | 10.216 | passed |
| online | rejections | 12.138 | passed |
| online | cycles | 12.698 | passed |
| startup_only | fixed | 7.349 | passed |
| missing_object | missing_object | 1.781 | passed |
| new_object | new_object | 1.871 | passed |
| wrong_version | wrong_version | 1.881 | passed |
| static_tls | static_tls | 2.294 | passed |
| tlsdesc | tlsdesc | 2.001 | passed |

The positive matrix covers dependency/reference lifetime, one restricted
isolated namespace, concurrent calls, already-running worker dynamic TLS,
lazy TLS, pthread_exit, last-worker cleanup, pin replacement resistance,
rejected flags/objects and repeated unload cycles. The separate startup-only
program proves the default dlfcn denial. Missing, substituted and wrong-version
objects fail before program use. The two real-ELF TLS mutations preserve
geometry and digests while requesting initial-exec or TLSDESC relocations;
both the production verifier and actual guest reject them before use.

The last-worker case checks the real GNU on_exit callback and TLS destructor
state. The NOLOAD case requires absence without a stale dlerror. GNU loader
reference and TLS-destructor rules govern unload; a successful dlclose does
not promise immediate release of a TLS-retained mapping or its process-long
approval pin. The five-second admission/recursive Files I/O budget is not a
hard timeout for arbitrary user constructors or destructors.

`qualification.json` binds the complete native system and both SDK identities,
the runtime, unwinder, all five approved controllers and both program stages.
The final guest input map, every evidence leaf, source inventories and complete
SDK snapshots were rechecked at export. Producer build receipts keep their
original built-not-run status; `guest.json` records the distinct execution.
The flat manifest covers every exported leaf. Serial files are lossless gzip
with deterministic timestamps; conversion metadata records raw identities and
explicit host-path templates without rewriting original producer receipts.

The frozen producer is local commit `86d39b31ade96ba7a609b9321e30ee63c0632441`. Public source commit
`0031e986cc79f0bb1d1f61a626def6a65d9dfb68` has exactly the same tree `94b1936c987f9b8662ef26e8b8f49bca38b1cb7a`. The runtime
uses the v2 capsule domain and the separately versioned generation-v2 online
record. Main's later v3 catalog-authority capsule is a distinct combination;
source integration or host tests do not qualify it as this executed profile.

The ordinary and ASan/UBSan host checks include six mapping/worker runs and
sixty production closure/verifier cases. LeakSanitizer was disabled. Three
earlier guest attempts remain failed: unsupported FAT geometry, missing online
approval fields at the GNU handoff, and an invalid version-mutation fixture.
The last diagnostic passed its earlier cases but failed overall; it is not
relabeled as the final qualification. The unsuccessful program link that used
the unavailable atexit fixture is also retained where recorded.
`failed_program_link_main.log` includes the original linker rejection of that
atexit symbol; its raw identity and the prior export manifest are recorded in
`conversion.json`. The original producer report and traceback are unchanged.

The contract excludes C++ online libraries, SMP, physical hardware, arbitrary
online search/admission, and runtime static-TLS/TLSDESC expansion. Default
fixed-startup denial remains intact.
