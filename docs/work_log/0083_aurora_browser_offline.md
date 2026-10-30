# 0083 Aurora Browser B0/B1: real local HTML/CSS on XOS

2026-10-29. **B0 PASSED (target compile/link); B1 PASSED (restricted local guest
subset).** B2 is BLOCKED by the absence of a qualified network service. HTTPS,
JavaScript and Internet browsing are not implemented/qualified. No Release.

Base freshly fetched upstream `39083f9968d84b5679c86a74a6c8394033c0d915`; PR16 merged,
PR17 open/unmerged when work began. The latter's fault-report implementation was
not imported. Separate branch `codex/aurora-browser-b1`, private worktree/build.
Network work stays in its own branch. No kernel/shared ABI/libc/Qt base changes.
The independent `browser_http` commit provides parser tests, not connected HTTP.

Delivered: exact liteHTML v0.9/Gumbo source archive + member hashes/licenses, XOS
cross builder, Qt QPainter container, bounded local read-only provider, Aurora
shell, actual address/history/reload/PS2 links/scroll/tabs/bookmarks, and local
start/reading/CSS/BMP/UTF8 fixtures. Source selection and comparison:
[engine evaluation](../plans/aurora_browser_engine_evaluation.md). Exact admitted
behavior/limits and future service separation: [contract](../contracts/aurora_browser.md).

Frozen system build `3fb1bb7d6b9e7bf9`, QEMU11.1.2 TCG, x86-64,1core,512MiB,
800×600. The target application links the already-frozen same-SDK Qt6.8.3
Core/Gui/Widgets archives; SDK artifacts are rehashed before build. Main's current
kernel/system is freshly built privately. No older Qt/GPU qualification is rebound
as a new whole-system acceptance. Full commands, compiler/tool hashes, SDK/static
library identities, ELF/system hashes, final source hashes and raw logs:
[qualification.json](../reports/aurora_browser_20261029/qualification.json).

## Actual guest checks

- VBE interactive: real CSS background pixel assertion (not only a screen capture),
  title/paragraph/text/link, actual PS2 anchor hit test, address navigation,
  Back/Forward/Reload, long-page PageDown/End, two independent tab histories,
  session bookmark creation, BMP callback and Latin/accented/Greek glyph screenshot,
  repeated document replacement and exact process resources after exit.
- Negative: missing page, unbalanced markup, depth17,32769-byte page, script tag,
  inline style with whitespace, huge HTML image dimension, CSS exponent, import
  loop/@rule,9-stylesheet quota and invalid external CSS are explicitly rejected.
  Corrupt BMP is omitted/logged. Valid navigation after engine/loader rejection
  succeeds; it does not leave the layout guard stuck. No app write/spawn/device
  capability is introduced by any URL or HTML attribute.
- Lifecycle: three normal launches/exits, killed browser, Display Service death
  causing browser exit72, service restart/new browser, exact counters, serial rescue
  and real file-service sync. No-display guest rejects startup explicitly and
  restores exact resources. Existing QPA input thread teardown is preserved.
- The full interactive suite also passes on a real VirtIO-GPU2D device with VBE disabled.
  Its start frame and the VBE frame have exactly equal1,440,000 RGB bytes
  (SHA256 `d6f3482f9a5298d88ce5be469741b0f1ef1b04339cdedf68862c014136521c17`).
  The five final browser suites contain47 passed checks; this is browser-scoped
  evidence, not a new whole-system/old Qt gate qualification.
- Each screenshot is actual QEMU scanout. Page HTML/CSS/BMP sources and hashes are
  retained. No static UI image is used as the browser or engine.

VBE sampled process pages:7127–7558 (max30,957,568bytes),3threads. Aurora's two
backdrop caches report3,840,000bytes. These are finite samples, not an absolute
memory peak, CPU benchmark or long-stress qualification. One current document is
rendered; inactive tabs store navigation state, then reload on activation.

## Failures retained

Initial target compilation exposed SDK include ordering (`include_next stdlib.h`)
and a wrong upstream enum spelling; both were fixed without libc stubs. Codeload
TLS retrieval failed; actual source is the successfully fetched pinned Git tree,
archived exactly with original licenses, not a guessed download hash.

The first guest runner passed its too-weak assertions while CSS had actually been
rejected: a digit-run check misclassified hex colors. Visual QA caught unstyled
content, retained its raw result/screens, and the final gate now checks actual
CSS-load logs and requested background pixels. CSS admission was replaced with
an explicit bounded property/value grammar; it is not a whole-Web sanitizer.

The first real-link test failed because liteHTML0.9 get_placement returns a zero
size, and large unpaced PS2 deltas did not land inside the glyph. The probe now
clicks inside the actual positioned anchor and paces sub127 movement; the actual
engine click callback/navigated document must both be observed. Earlier failures
and successful intermediate runs remain in the report's `iterations/`.

## Reproduce and handoff

`src/ports/aurora_browser/build.py` takes explicit matching `--sdk`, `--qt-build`,
`--qt-source`, `--host-qt`, `--binutils`, `--output` paths. It verifies the original
archive/member hashes and SDK, then builds GumboC99, liteHTMLC++17, Aurora/QPA and
the actual static XOS ELF. Local target:
`build/browser/target/aurora.elf`; system:`build/browser/final-system/xos.img`.
Tests:`tests/aurora_browser_acceptance.py` with interactive/negative/lifecycle,
and `tests/aurora_browser_no_display.py`; each takes image/payload/output explicitly.
QEMU command lines are recorded; standard startup remains `-nic none`.

No public binary/static Qt distribution is qualified. Original third-party
licenses and exact sources are present; material audit does not replace member,
source/relink or redistribution review. Future work: authenticated network service
and N2 first, then controlled HTTP provider/B2; TLS/CA/time/entropy and JavaScript
are separate gates. No complete modern-site, Chrome/Firefox, GPU Web rendering or
arbitrary hostile-content safety claim.

Material audit (7 SDK materials), docs consistency (458 links/66 syscall/73 historical sources),
ABI consistency and whitespace checks pass. Full static Qt license/relink and
member-level review remain NOT_RUN. No new binary Release or main push.
