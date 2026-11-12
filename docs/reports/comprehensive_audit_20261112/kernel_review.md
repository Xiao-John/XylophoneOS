最终基线已补审至 `4c9b6f8feb0667d7169167e406da662be789876c`。以下保留早期阶段的验证计数与状态，尤其 e624 阶段的 IPC unsupported 描述已由上游 #114 更新；当前状态和增量结论以 `latest_upstream_review.md`、总报告及最终结果为准。

本附件合并分阶段审阅记录。阶段内计数不相加；最终覆盖与结果以 `repository_inventory.csv` 和 `validation_results.json` 为准。宿主绝对路径已机械替换为 `${XOS_ROOT}`、`${XOS_AUDIT_WORK}` 等占位符，以下不是未经处理的原始日志。临时清单名仅用于说明记录来源；本报告附有最终 CSV、结构化结果、关键日志与可重放命令。

# Kernel, boot and shared ABI audit — 2026-11-12

Phase baseline: e6246faf8eefac305a99528f727b1592ee93a5b2.

Scope: all 74 files listed in kernel_audit_files.txt (src/kernel, src/boot, src/shared). Read the complete first-party contents, including all 5,397 lines of tasks.cpp, page tables, memory ownership, VM continuation/pins/COW, IPC v1, platform devices, shared ABI and BIOS loaders. This is source review, not a proof that every path is correct.

## Fixed K1 — process completion stolen while a waiter is ready

File: src/kernel/arch/x86_64/tasks.cpp, sys_process_wait.
Trigger: thread A blocks waiting for child, keeping a pin on its process_status output; finish_task publishes the ready completion and marks A ready; thread B in the same parent runs before A and waits for the same child. The old ready branch consumed the completion before checking for an existing waiter. When A resumed, deliver_wait could no longer find the completion and returned without clearing its wait_kind/user_pin; syscall frame still reported success, output was not delivered, and the leaked pin prevented later VM unmap/decommit.
Correction: existing duplicate-waiter check now precedes ready completion consumption. Existing nonblocking pending result (would_block) is preserved. No locks or speculative race machinery were added.
Regression: tests/kernel_process_wait_race_test.py extracts the exact current process/thread records, wait case, completion lookup, finish_task, deliver_wait, user range/copy and owned_process functions from tasks.cpp, includes actual lifecycle/pin/ABI headers, and compiles a Linux host harness. Page-table lookup, scheduling and unused device teardown hooks are substituted; guest memory is actually mmap'ed and process_status crosses a page boundary. Both blocking and polling competitors, pending duplicate, successful delivery, pin release and exactly-one consumption pass. Running the same test with --source on HEAD's pre-fix tasks.cpp fails the ready-owner assertion deterministically. This is not a scheduler/guest qualification result.

## Fixed K2 — debug monitor repeated alloc loses a physical page

File: src/kernel/core/console.cpp, command_alloc.
Trigger: alloc, alloc, free. The monitor remembered only the latest allocation, so the first page remained allocated with no command able to free it.
Correction: reject another alloc with alloc result=busy while the tracked allocation is still owned. Existing alloc/free and double-free behavior is unchanged.
Regression: tests/kernel_smoke.py now requests a duplicate alloc and expects busy before freeing. Guest smoke was NOT RUN because the pinned toolchain/NASM/QEMU are unavailable. Separately compiled the actual console.cpp and memory.cpp in a temporary Linux host harness, mmap'ed two physical pages, and exercised alloc/alloc/free/free. Pre-fix failed preserved ownership/free count assertion; fixed code restored the two-page baseline. Only debug output was stubbed. The temporary test did not touch build/.

## Additional verification

All 22 default kernel/shared C++ translation units compiled to independent host objects with repository COMMON_FLAGS + X86_FLAGS, including -Werror/-Wconversion/-Wshadow, using g++ from PATH. The earlier g++ 12 label was a recording error; no version-specific g++-12 executable was selected. The current compiler resolves to /usr/bin/x86_64-linux-gnu-g++-14 and reports g++ (Debian 14.2.0-19) 14.2.0. The original object run did not separately capture --version output. tasks.cpp, paging.cpp and cow1_self_check.cpp also compiled with VM1/COW1 enabled (3 additional objects). Generated image headers were declaration-only substitutes (no bootstrap bytes), so this does not validate the image generator, linker layout, assembly, pinned compiler or guest boot. Full log: kernel_audit_validation.txt. Console additionally compiled and executed after its small follow-up fix.

## Established unfinished work and verification gaps

1. COW2 copyout/pin guarantees are explicitly incomplete, per docs/work_log/cow1_snapshot_progress.md and docs/contracts/cow0.md. Current isolated probe may privatize earlier pages before later OOM/readonly rejection; normal fork remains eager. This audit leaves the opt-in fence intact. Completing COW2 requires transactionally prepared copyout for all fixed outputs, short-read prefix semantics, failure classification and guest fault-injection coverage, not just enabling a flag.
2. Real parent-exits-first COW validation is incompatible with current process-tree teardown (finish_task recursively kills children). COW-L1/L2 lifecycle/domain work is recorded upstream. Altering parent/child lifetime would change project behavior and is not a local bug fix.
3. IPC v1 endpoint, notification and wait-set implementation exists, but feature mask remains unsupported pending guest qualification. A host model or this source audit cannot qualify real blocking delivery/close/deadline/cancellation. Preserve existing advertised masks and complete the actual acceptance matrix with matching manifests.
4. sys_device currently validates request headers and buffers but valid operations still return device_unknown; grant/map/DMA/IRQ/revoke backend segments 1b–1e are not implemented. This is recorded staging, not a completed device authorization subsystem.
5. No NASM assembly, cross-link, boot, real interrupt/CR3/TLB/FPU/PIO/MMIO/DMA behavior or firmware hardware matrices ran in this environment. BIOS loaders/platform code were read; changing uncertain hardware behavior without those checks would not be responsible.
6. Legacy ATA PIO and VirtIO-GPU work includes bounded synchronous polling in non-preemptible kernel paths. No measured latency result is available here. Migration to user drivers/device authorization is project work and requires actual hardware/guest timing rather than guessed limits.
7. Historical COW0 evidence is immutable. Its --check scanner is expected to report source drift against the old audit after COW1 and these fixes. Create new evidence for this revision; do not overwrite the frozen baseline.

Unconfirmed suspicions (not reported as bugs and not patched): RTC centuries-long signed-range overflow, exotic firmware register clobbers, ambiguous IPC call deadline=0 reply semantics, and duplicate defensive range validation. No speculative complexity was added for these.


---

# Ports, runtime preparation and vendor boundary audit — 2026-11-12

Final review baseline: e6246faf8eefac305a99528f727b1592ee93a5b2. Parent fast-forwarded to this upstream revision during the audit; it only added UTF-8 M2 tests/docs, not the implementation reviewed here. Complete additional reads: 90 files in kernel_ports_audit_files.txt. Partial/supporting reads are explicitly separated in kernel_ports_audit_partial.txt. Core kernel/boot/shared coverage remains 74 files in kernel_audit_files.txt. These counts describe source reading, not correctness proofs or a claim to have read every vendored upstream file.

## Fixed P1: Adventure readline spins forever at pipe EOF

Source: src/ports/adventure/xos_readline.cpp.

A closed writer makes read(0) return zero; the old shim treated this exactly like process_error_would_block and yielded forever. An empty piped input therefore never terminated, and an unterminated final line was never returned. The real console read ABI uses would_block for an empty console, so zero can retain its EOF meaning. The fix yields only on would_block, returns accumulated bytes at EOF, and frees/returns null for empty EOF.

Regression: tests/adventure_readline_test.py compiles the actual shim and SDK declarations. A syscall adapter forwards handle reads to actual host POSIX pipes; no synthetic line-reader logic is copied into the test. Empty EOF, partial-line EOF, newline then EOF pass. The original HEAD implementation deterministically fails the explicit unexpected-yield assertion. This does not qualify real UART input or the entire Adventure program in XOS.

## Fixed P2a: SQLite journal location follows a changed cwd

Source: src/ports/cpython/sqlite/xos_vfs.c, xFullPathname.

Previously xFullPathname copied relative input unchanged. SQLite retains that filename to derive a rollback journal later. Opening a database by a relative path, changing cwd, and starting a write transaction can therefore create the journal in the new directory while the already-open descriptor still names the original database. The fix expands relative paths using getcwd and lexically collapses repeated separators, dot and dot-dot components into a bounded absolute path. XOS has no symlinks, and a new database need not exist, so realpath is neither needed nor appropriate. Short output buffers still fail explicitly.

## Fixed P2b: SQLite VFS aliases use independent lock records

Source: xOpen, xLock and xCheckReservedLock in the same VFS.

The previous lock table compared path strings. Different names of the same database could bypass its in-process conflict check. Each successful open now records the actual fstat st_dev/st_ino, and conflict checks use that identity. A failed fstat closes the newly opened descriptor and returns SQLITE_IOERR_FSTAT. This uses the existing file-service identity contract, not a new registry or invented identifier.

The userland audit confirmed that XOS fstat supplies st_dev=1 and a non-reused inode derived from the resolved FAT directory entry (sector/offset). LFN/SFN and ASCII-case aliases share it. Live opens prevent delete/rename/replacement, so the identity stays stable. IDs exhaust explicitly rather than silently becoming zero. **Current FS-01 writable-open exclusion often rejects a second writable open before SQLite VFS locking is reached. We did not reproduce guest concurrent-writer database damage and make no such claim.**

Regression for both SQLite changes: tests/sqlite_vfs_paths_test.py plus tests/sqlite_vfs_paths_test.c compile the actual VFS with the unmodified pinned SQLite 3.54.1 amalgamation and official sqlite3.h. The archive came from https://www.sqlite.org/2026/sqlite-autoconf-3540100.tar.gz; length 3332984, SHA256 926ef8d3eab93fbf6e06011901273eec076b25594a4e1cdadd50c987f4f6d64e and SHA3-256 b6ced585c750916b1052667239a12c25a7ff34e7f06e1e6e01ecb0427657d9c4 matched the repository lock. No VFS ABI structure was hand copied. Real SQL transactions check alias BUSY, lock release after rollback, and a journal next to the original database after chdir. A host hardlink exercises equal device/inode with different names; XOS hardlink support is not claimed. The fixed VFS passes and the original VFS fails its canonical-path assertion. No SQLite guest run or crash/reboot qualification occurred.

## Fixed P3: dash pipeline corrupts routes when stdout is closed

Source: src/ports/dash/admission_xos.c, xos_evalpipe.

With fd 1 initially closed, pipe() can return its read end at fd 1. The old dup2(write_end, 1) then destroys that read end and the writer fails with a broken pipe. The fix moves any newly created pipe endpoint at fd 0–2 to an available descriptor at least 3 with the existing F_DUPFD_CLOEXEC API before installing routes. Existing unwind cleanup owns the updated descriptor array, including a failure partway through moving the ends.

Regression: tests/dash_pipeline_fds_test.py extracts the complete real xos_evalpipe function and uses real host pipe/fcntl/dup2/read/write/close. Two bounded stage callbacks transfer bytes; parser, actual process launch/fork and redirection unwinding are not exercised by this host test. All four initial stdin/stdout open/closed combinations pass, preserving final stdio state and leaving no new fds in the checked 3–31 range. Original source deterministically fails the real write when stdout starts closed.

## Fixed S1: a rejected ABI output directory still mutates immutable input

Source: scripts/build_cpp_abi_probe.py.

The existing code detects that output-root is equal to/inside the SDK or runtime prefix and raises ManifestError, but its outer error handler writes cpp_abi_build_report.json into that same rejected output-root. An ordinary bad CLI argument therefore changes an input explicitly declared immutable and invalidates its hash. The fix moves those existing overlap checks into the initial preflight, before a report-writing exception path exists. No new policy or repeated internal checks were added.

Regression: tests/cpp_abi_output_test.py invokes the actual CLI against temporary SDK/runtime directories. Four bad output placements return 2 and leave the input files byte-for-byte unchanged, without creating the rejected child directory. A separate legal output still receives a useful not_ready manifest error report. Current code passes; HEAD's original CLI deterministically modifies the SDK and fails the regression. No compiler or mock build is involved.

## Documentation corrections and remaining limitations

CPython xos_time.cpp is still an independent compatibility bridge that busy-spins for sleep; the newer threading runtime already exposes blocking sleep. The stale claim that XOS has no blocking sleep service was corrected in its comment and README. The weak times wrapper is also now described as delegating to the selected SDK's _times, rather than promising ENOSYS regardless of SDK. Runtime behavior was not silently changed for older SDKs. Migrating this bridge should bind the supported SDK and rerun actual CPython sleep/thread tests. The port still documents deterministic Python hash secrets, no CPU-time accounting, bounded stacks and disabled POSIX facilities; these remain explicit profile limits requiring separate integration/acceptance, not evidence that this audit implemented those features.

All six assigned external port adaptation trees were read for first-party C/C++/headers/patches. GCC/binutils runtime preparation scripts were read completely, but their full upstream toolchains could not be rebuilt without the pinned cross tools. Existing source locks, frozen manifests and guest evidence were preserved. No claimed readiness flag was upgraded because a host test passed. GCC source patch reapplication and optional runtime archive variants were considered but lacked a reproduced defect; no speculative edits were made.

Third-party boundary review covered FatFs README, ffconf.h, ff_string.h, diskio.h, local FILINFO identity fields/get_fileinfo assignments, and newlib README. FatFs is intentionally single-volume, static-LFN workspace, non-reentrant, UTF-8 API with ASCII-only case/OEM adaptation, bounded object locks and no RTC timestamps. Those are current profile choices, not newly fixed bugs. The local identity fields match the service's lookup basis. At this earlier phase, the complete upstream ff.c and all vendored newlib headers had not yet been read line by line. A subsequent full-read phase completed all 140 visible third-party text code files and the six original Make sources; see third_party_review.md and third_party_full_reads.txt. Prebuilt archive implementations remain outside the source-audit claim.

## Reproduce the new regressions

Run from the repository root (all temporary compilations stay outside shared build/):

    python3 tests/kernel_process_wait_race_test.py
    python3 tests/adventure_readline_test.py
    python3 tests/dash_pipeline_fds_test.py
    python3 tests/cpp_abi_output_test.py
    python3 tests/sqlite_vfs_paths_test.py --archive ${XOS_AUDIT_WORK}/sqlite_vfs_audit/sqlite-autoconf-3540100.tar.gz

The SQLite runner also accepts the builder's normal cache location by default. The optional --source/--vfs/--script arguments permit running the same real-implementation regressions against saved pre-fix sources. Parent owns final integrated checks, commits and delivery. No shared build directory was written by this agent.


---

# Third-party visible source and integration audit — 2026-11-12

Phase repository baseline: `e6246faf8eefac305a99528f727b1592ee93a5b2`. This is a source/integration review plus narrowly scoped host regressions, not a guest or complete dependency qualification.

## Exact reading coverage

`third_party_full_reads.txt` records **143 distinct, completely read files / 33,096 lines** added in this phase:

| Scope | Files | What was read |
| --- | ---: | --- |
| `src/third_party/newlib/x86_64-elf/include` | 135 | All headers: 66 top level, 19 machine, 7 ssp, 43 sys |
| `src/third_party/fatfs` | 2 | Complete `ff.c` (7,259 lines) and `ff.h` (450 lines), including disabled branches |
| `src/ports/make/upstream/make` | 6 | Complete `defaults.c`, `main.c`, `make.h`, `parser.c`, `posix.c`, `rules.c` (2,260 lines total) |

The earlier complete-read list `kernel_ports_audit_files.txt` already includes the other three FatFs code headers (`ffconf.h`, `ff_string.h`, `diskio.h`). The two lists therefore cover **all 140 tracked text code files under `src/third_party` / 31,242 lines**, plus the six Make sources. Counts were compared with `git ls-tree` of the exact baseline; no missing text code remained under these two scopes. The phase list contains actual complete reads, not filenames merely obtained by search.

The three third-party readme documents were covered in the earlier integration review. `COPYING.NEWLIB` is license text, not implementation code. **The two vendored `libc.a`/`libm.a` archives were not audited as source.** Likewise, pinned upstream archives outside these visible trees, generated build outputs, toolchain binaries and a running XOS system are outside this full-read claim. Reading all visible headers cannot expose every implementation inside an archive or prove all branches correct.

No third-party source, generated header, lock file, frozen source/evidence or shared `build/` content was modified by this phase.

## Fixed integration defect: failed O_TRUNC cleanup loses the live FatFs object

**Changed:** `src/user/services/files.cpp`; extended the existing real-FatFs fixture at `tests/fixtures/file_semantics/file_semantics.cpp` by one case (24 to 25).

### Trigger and impact

1. Open an existing nonempty file with `write_only | open_truncate`, without `open_create`.
2. The service successfully obtains a `FIL`; `f_lseek`/`f_truncate` dirty the real FAT metadata.
3. Make the actual disk backend return `RES_ERROR` for `disk_write`. `f_sync` fails while flushing the dirty FAT window, before it can finish updating the directory entry.
4. The error branch then calls `f_close`, which also fails because the disk failure persists.
5. The old branch discarded the close result and reset the whole `open_description` anyway. FatFs only decrements its object-sharing lock and invalidates `FIL` after a successful close; this reset loses the only live `FIL` that can release the lock.

The service returned an I/O error and no user handle, but retained a FatFs sharing lock without any object registered for cleanup. Later opens of the same file remained blocked after the transient disk failure ended, and repeated occurrences could consume the bounded lock table. This is an ordinary I/O-error path, not a speculative scheduling race.

### Minimal correction

As soon as `f_open` succeeds, record `description.used` and its path. References remain zero until a user handle is successfully installed. On the truncation/synchronization error path, call the existing `cleanup_description` routine. That routine retains the object if close fails; the existing zero-reference cleanup sweep retries it. The successful-open path still sets the normal reference count and flags. No new state machine, retry scheduler, lock or broad I/O redesign was added.

### Actual implementation regression

The fixture includes the actual service implementation and compiles the repository's actual `ff.c` and `fatfs_unicode.cpp`. It uses the existing memory-backed disk harness and a real FAT image. Fault injection is only at the disk-write boundary; neither `f_sync`, `f_close` nor their lock bookkeeping is mocked or copied into the test.

The new case seeds a six-byte file, arms a persistent disk-write fault, performs the real truncate-open request, and verifies an I/O error with no returned handle. It explicitly requires two disk-write errors at that point, proving both the original sync and cleanup close failed. It retries cleanup once while the disk still fails, clears the fault, retries again, reopens the same file, verifies the zero length, closes it, and checks that all descriptions are released.

| Version | Result |
| --- | --- |
| Working tree before this additional fix, including the previous userland audit fixes | Exit 1: `FAIL truncate failed close releases lock after cleanup retry` |
| Same fixture and existing 24 cases after this fix | Exit 0: `FILE_SEMANTICS_CASES_PASSED=25` |

Evidence is in `fatfs_truncate_audit/before.json`, `after.json`, and `files_before.cpp` in the workspace parent. The recorded pre-fix source SHA256 is `40c8347976fff9cb1ae287ea55cf89c188e99df97e2251efc0e33694292ce566`; fixed source SHA256 is `3bee5aaf877808131da25ce8c8961f6defc4946b4ffe3cdcec58432b6a4d46ea`; fixture SHA256 is `7c1486fcb8106f36ae516dbb2c10b925eb906206c3d321198fdb213119708c90`. Those identify this precise before/after experiment; the before file is not claimed to be pristine upstream baseline code.

Both recorded compilations used `/usr/bin/g++`, resolved to `/usr/bin/x86_64-linux-gnu-g++-14`, reporting `g++ (Debian 14.2.0-19) 14.2.0`. Complete compile commands are recorded in the JSON. They used the existing host fixture's flags and private files outside shared `build/`. No guest disk-driver, reboot or power-loss test ran.

A first exploratory fault placed only at `CTRL_SYNC` did not exercise failed `f_close`: in that branch, this FatFs version has already cleared `FA_MODIFIED`, so the next close can succeed. The final regression deliberately uses actual persistent `disk_write` errors at the earlier dirty-window flush boundary. The evidence must not be described as a `CTRL_SYNC` reproduction.

## Two confirmed dependency-header compatibility issues, left for a pinned SDK follow-up

Temporary source probes and full diagnostics are saved in `newlib_header_audit/`. The probes include the actual vendored headers; they do not reimplement the macros. They were compiled by `/usr/bin/gcc`, resolving to `/usr/bin/x86_64-linux-gnu-gcc-14`, version `gcc (Debian 14.2.0-19) 14.2.0`, with `-std=gnu11 -ffreestanding -isystem <vendored-include> -fsyntax-only`. `results.json` records commands, compiler identity, exit codes, diagnostics and hashes of the relevant headers. These are host compiler findings, not pinned cross-compiler acceptance results.

### H1 — newlib stdatomic initialization macros mismatch GCC's native _Atomic

`stdatomic.h` correctly chooses native GCC atomics for GCC >= 4.7, and `sys/cdefs.h` consequently leaves `_Atomic(T)` as the native scalar type. However, the non-Clang initialization macros still use the old structure wrapper's `.__val` member.

A C11 source with `atomic_int value = ATOMIC_VAR_INIT(0)`, `atomic_flag flag = ATOMIC_FLAG_INIT`, and `atomic_init(&value, 1)` fails with field-initializer / non-structure-member diagnostics. The probe includes `stddef.h` and `stdint.h` first so these diagnostics isolate initialization, rather than unrelated standalone-header type availability. Other GCC atomic operations use the native object directly, so changing an application to the old wrapper type is not an appropriate workaround.

**Impact boundary:** this is reproducible when this newlib header is selected. `prepare_gcc_seed.py`'s C-only profile uses `-isystem /sysroot/include`, which gives it priority over compiler-owned system headers. The C++ bundle path explicitly switches to `-idirafter`, and the current `xos_app.py` also uses `-idirafter`. The delivered GCC seed manifests contain their own `stdatomic.h` and `tgmath.h`. Those paths can select the compiler-owned header first. No current first-party source including this newlib `stdatomic.h` was found, and no guest failure is claimed.

**Follow-up:** reproduce with the fixed GCC 16.2.0 cross compiler and actual delivered GCC 16.2.0 seed, separately exercising the exact C-only/C++/application profiles; then either carry a narrow patch through the repository's newlib source/candidate build pipeline or consistently choose the compiler-owned header where the profile permits. Rebuild the SDK and its provenance/acceptance evidence. Do not manually edit this generated/vendored include tree or silently replace toolchain locks.

### H2 — newlib tgmath loses the requested floating-point type

In the current x86_64 header configuration, `_LDBL_EQ_DBL` is undefined. The fallback `__tg_impl_simple` uses a conditional expression between the double and float functions and has no long-double arm. Thus even a float call gets the conditional expression's double result type, while a long-double input can choose the float function and lose precision/range.

The exact header fails both compile-time checks that `typeof(sqrt(1.0f))` is `float` and that `typeof(sqrt(1.0L))` is `long double`. This confirms the type-dispatch defect without linking to a substituted math implementation. It does not establish which long-double functions exist in the prebuilt target archive.

**Impact boundary and follow-up:** the same include-priority distinction as H1 applies. Use fixed GCC 16.2.0 cross/actual-seed profile-specific compile/link probes to establish exposure and available long-double implementations; then patch/rebuild from source or select the compiler header through a reviewed profile change. This audit does not claim every existing XOS math caller is affected. The `sys/cdefs.h` alignment-helper suspicion was separately compiled successfully and is not a reported defect.

## FatFs integration constraints checked

- The locally added `FILINFO.xos_dir_sector` / `xos_dir_offset` fields are assigned from the actual SFN directory slot in `get_fileinfo`. This agrees with the file service's identity table and lets long name, short alias and ASCII-case spellings share identity. The header's 16-bit `ino_t` limit also agrees with the service's bounded non-reused ID policy and explicit exhaustion behavior from the earlier userland fix.
- `FF_USE_LFN=1` gives FatFs a static LFN workspace and `FF_FS_REENTRANT=0` provides no internal concurrency protection. Current service calls are serialized; adding direct concurrent callers would require changing that ownership contract, not merely enabling a macro. `FF_FS_LOCK=32`, one volume and 512-byte sectors remain explicit bounds.
- The API uses UTF-8 (`FF_LFN_UNICODE=2`) with the existing ASCII-limited OEM/case adapter. FatFs's own UTF-8 decoder does not enforce every shortest-form rule, but the service entry's `normalize_path` already calls strict `xos::text::valid`. This is not a reason to add repeated internal validation or modify upstream decoding without a reachable bypass.
- Writable FatFs `f_lseek` may allocate past EOF without zeroing the new range. The service's own logical-position and `grow_with_zeros` layer provides the advertised zero-gap behavior; directly exposing raw FatFs seeking would be a different API.
- `f_close` failure preserves object ownership; this constraint is the source of the concrete O_TRUNC fix above. Other close paths already use the retained zero-reference cleanup policy.
- The reviewed upstream code has limited durability semantics: secondary FAT-copy and FSINFO write outcomes are not propagated in every helper, and rename spans multiple metadata updates. These observations are not a demonstrated guest data-loss result. The project must not broaden its bounded file/journal contracts to arbitrary power-loss atomicity without targeted disk-error/crash tests. No upstream durability rewrite was attempted.
- Optional exFAT, variable sectors/LBA64, relative-path directory state, mkfs, labels, chmod, expand, fastseek, trim, string-output and forward APIs were read as visible source branches; disabled code is not a delivered capability.

## Make upstream versus adapted executable

The six original Make sources were read with `src/ports/make/patches/0001_xos_always_build.patch` and the port README. The patch already replaces the original recursive dependency check with visiting/completed state and a cycle error. The original `depends` implementation therefore is not reported as a current project bug. The XOS target builds the four adapted engine C files with the local `posix_xos.cpp` backend; original `posix.c` remains visible upstream source, not the guest backend. The explicitly bounded serial `-B` profile does not promise full GNU/POSIX Make, implicit-rule support or timestamp-based incremental builds. No unadapted-backend behavior was turned into an unsupported product bug claim.

## newlib interface and configuration boundaries

The visible base headers identify newlib 4.6.0. Their base `newlib.h` disables `_MB_CAPABLE` and retargetable locking and defines `_MB_LEN_MAX=1`; that base snapshot must not be mistaken for the separately built UTF-8/threading SDK candidate. `sys/reent.h` exposes configurable global, dynamic-reent and thread-local layouts, so header/library configuration must be kept matched. Reading a threaded branch does not qualify the base archive for concurrent libc calls.

The x86_64 interfaces use 64-bit long/off_t/time_t but a 16-bit `ino_t`; FatFs file offsets have their own narrower bound checked at the service boundary. The configured `_READ_WRITE_RETURN_TYPE` is `int` in this base newlib, so source declarations must be checked against the actual target headers, not assumed to equal the host's `ssize_t`. The current adapter and bounded transfers were checked against those declarations.

Generic header constants and declarations are not evidence that every POSIX facility exists. Examples include the intentionally unsupported base `sys/dirent.h` replaced by the XOS SDK overlay, optional machine-dependent C11 threading, signal features and generic limits. Queue/tree macros, stdio/reentrancy layouts, signal/time definitions, ABI/ELF structures, floating-point/endian definitions and all fortify wrappers were read, but this does not audit the bodies inside the prebuilt C/math libraries.

## Remaining validation limits

No fixed GCC 16.2.0 x86_64-elf compiler, actual seed execution, NASM, QEMU or guest acceptance was available in this environment. No cross-link, boot, real device failure, filesystem reboot recovery, toolchain rebuild, optional SDK profile qualification or binary-archive implementation audit was completed. The parent agent owns integrated final tests and commits. Existing readiness masks and frozen evidence remain unchanged. A full visible-source read is a coverage statement, not a promise that all bugs have been found.
