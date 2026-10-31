# LP0 — LocalPilot as an ordinary XOS AI-native consumer

2026-10-30. Dependency research and mapping, **not a LocalPilot port**. Authorized
private source was inspected read-only at its freshly fetched main. Exact private
source identities/manifests are retained only in a private local audit receipt outside this checkout;
no private source, lockfile, credentials, runtime state or configuration is included
in this public document. No Mac application, model, configuration or workspace was changed.

## Capability and implementation matrix

| Layer | Same source opportunity | XOS dependency / current gate | Next concrete probe |
|---|---|---|---|
| Python Agent Core / API 1.0 | Preserve business code, task state machine, Permission Gateway, receipts and UNKNOWN | Existing restricted CPython does not establish full socket/TLS/process/extension support; several native libraries require ports | On a lawful network/runtime combination, import actual dependency closure; run API auth/refusal/task-state/SSE/disconnect tests unchanged |
| HTTP/SSE/model connections | Preserve existing protocol and identity/egress decisions | Qualified userspace network, TCP/DNS, TLS/CA/hostname/time/entropy, cancellation/backpressure and stream lifetime are BLOCKED | First local authenticated SSE conformance service; then explicit-authority TLS model endpoint; no certificate bypass/HTTP downgrade |
| React/TypeScript UI | Keep original app source and branded interaction; add a narrow host adapter | DOM/events/modern CSS/modules/fetch/streaming/origin model are absent from liteHTML + QuickJS | Modern engine fixture with actual React state/event update, module loading, streaming fetch cancellation and origin denial |
| Tauri 2 / Rust desktop | Preserve commands/types when a platform runtime exists | XOS Rust target/std, atomics/TLS/unwind/files/process/net bindings, Wry/Tao/runtime/event loop and actual WebView are unported | Compile/link a minimal Rust target ELF; then real host window + WebView + authenticated command/event roundtrip |
| Native host dialogs/files/notifications | Reuse business-facing command API | Generic per-window file-selection authorization, notification broker, clipboard and live settings are not implemented | Denied/stale scope and lifecycle probes before real grants |
| Suite / Companion | Preserve independent service lifecycles | Launch supervision, service readiness, storage, watchers, process accounting and platform observers need qualification | Bounded launch/restart/stop and credential isolation receipts; never fake watcher or process info success |
| Channel bridges | Retain Node protocol adapters where runtime support exists | Node/libuv/network/stream/process support is not established by QuickJS language execution | Actual Node runtime closure and local bridge protocol refusal/reconnect tests |
| Pet / bubbles | Retain app behavior and artwork only under its source license | Transparent bounded overlay windows, input-region passthrough, drag capture, screen constraints, layers/focus and revocation await G2 | Two independent windows + bubble, real hit tests, parent death/close and resource-return gate |
| Computer Use / SSG | Preserve approvals, task receipts, scope and UNKNOWN; prefer stable semantic references | App-local SSG exists as a prototype; cross-process discovery/authorization/aggregation and action transport are BLOCKED | Broker authenticates application/session epoch + node/version + operation lease; test revocation/target replacement before OS actions |
| macOS APIs | Platform adapters must be replaced | AppKit, Swift observers, Accessibility and ScreenCaptureKit are not XOS APIs | Real XOS implementations or explicit unsupported results; never success stubs |
| MLX / local inference | Optional backend | MLX is not required for XOS | Use an already-authorized external HTTP/TLS model service through the existing Egress and credential boundaries |
| Native package / Code - OSS | Keep future platform work separate | XPK installation, architecture/ELF support, modern Web engine and large runtime closure remain distinct gates | First package a real small XOS host with uninstall/lifecycle receipts; no macOS binary compatibility claim |

[Tauri 2's WebView documentation](https://v2.tauri.app/reference/webview-versions/)
describes its dependence on real platform engines. The upstream
[Wry implementation](https://github.com/tauri-apps/wry) and
[Rust target documentation](https://doc.rust-lang.org/rustc/targets/index.html)
are platform references. Their existence does not establish an XOS port. A Rust
target JSON or a static front-end bundle alone would prove neither Tauri nor
LocalPilot end-to-end operation. macOS arm64 DMGs do not execute as x86-64 XOS ELFs.

## Aurora → React mapping

The implemented `theme_json()` descriptor is version 2 and process-local.
`theme_css_variables()` emits declarations only. A future authenticated host may
apply these to its own `.xos-aurora-host` root and notify that same app on changes.
Never inject them into arbitrary third-party page bodies or cross-origin frames.

| Native role | Scoped CSS variable | Host use |
|---|---|---|
| text / muted | `--xos-aurora-text`, `--xos-aurora-muted` | Application chrome, with stable content contrast |
| content / control | `--xos-aurora-content`, `--xos-aurora-control` | App shell and standard fields |
| accent / focus / danger | matching `--xos-aurora-*` | Preserve LocalPilot branding while using native feedback roles |
| grid / inset | `--xos-aurora-grid`, `--xos-aurora-inset` | px; density/layout shared with native controls |
| panel/control radius | `--xos-aurora-panel-radius`, `--xos-aurora-control-radius` | Concentric shell geometry |
| body font/family | `--xos-aurora-font-body`, `--xos-aurora-font-family` | Existing licensed DejaVu fallback, not proprietary Mac fonts |
| hover/switch duration | matching `*-duration` | ms; zero under reduced motion |
| high contrast / transparency / quality | JSON policy fields | Host chooses opaque/fallback treatment; CSS does not grant background capture |

CSS mapping generation is implemented; React consumption and authenticated theme
transport are **NOT_RUN / BLOCKED**. The original UI is not replaced by a new
LocalPilot implementation or a static screenshot.

## SSG adapter and authority

Observe → Propose → Authorize → Execute → Verify are separate responsibilities.
LocalPilot can consume bounded SSG snapshots/diffs instead of discovering every
target through screenshots. It must pass a stable source epoch + node identity +
expected scene/state version, a specific operation and the existing Permission
Gateway's allowed scope to a future trusted userland adapter. Discovery and model
output cannot create a lease. Browser text, document content, names and tool
results remain untrusted, including strings that look like instructions.

The adapter must translate SSG action requests into generic application/window
interfaces. It cannot call a LocalPilot-only syscall or broaden an observation
lease into file/network/screenshot/input authority. Host action receipts retain
the existing API 1.0/SSE task model and UNKNOWN; a lost external response cannot
trigger automatic replay. Structured verification must observe the resulting
application state, not trust an agent's assertion of success.

For apps lacking semantics, prefer an app-supplied object model or explicit custom
render labels. Otherwise return SEMANTICS_UNAVAILABLE. An image fallback is a
separate authorized observation with provenance/confidence, never an inferred
right from theme adoption. No guest OCR, real-model, production LocalPilot,
remote inference or Computer Use qualification is claimed by LP0.
