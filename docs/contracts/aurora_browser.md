# Aurora Browser local HTML/CSS prototype

2026-10-29. Application policy, not a new kernel ABI. The implementation uses the
existing Qt 6.8.3 Widgets/QPA and `libXosAurora.a`, one fullscreen native window,
and the real pinned liteHTML 0.9 layout engine with bundled Gumbo HTML parser.
The engine is independent of the local-file provider and Aurora navigation shell.
No QtNetwork, WebEngine, fake socket/POSIX function or app-name privilege is added.

## Content and UI

The editable address bar accepts `file:/web/...` or `/web/...`; relative links and
resources resolve under the current local document directory. `..` is normalized,
then anything outside `/web/` is rejected. Colons except the removed `file:` prefix,
percent encoding, backslashes, query strings, NUL and addresses over256 characters
are rejected. Fragments resolve to the same document; scrolling to named anchors
is not implemented. The consumer only opens files read-only; a URL never grants
write, device, spawn or kernel rights. No download or file execution feature exists.

Back/Forward/Reload, PS/2 link click, keyboard PageUp/PageDown/Home/End and scrollbar
are real operations. Ctrl+L focuses the address bar; Alt+Left/Right navigates history;
Ctrl+R reloads. Up to4 in-window tabs hold separate history/index/scroll state;
Ctrl+T opens one and Ctrl+Tab switches. Each history is bounded to16 entries.
Three supplied bookmarks and up to4 added session bookmarks perform navigation.
Session bookmarks are not persisted. The Close button/Escape exits the application.
There are no extra native windows or nonfunctional navigation controls.

Only the surrounding Aurora chrome uses cached glass. The page is painted as its
HTML/CSS requests. Background/soft-environment caches regenerate on resize, not on
address typing. Rendering is QPainter CPU raster; VirtIO-GPU2D is scanout, not GPU
Web rendering or OpenGL/Vulkan acceleration.

## Admitted subset and limits

Gumbo parses admitted HTML; liteHTML computes block/inline/flex layout and positions;
Qt shapes/rasterizes fonts and paints text, solid rectangular borders/backgrounds,
and bounded BMP images. These are actual engine callbacks, not an image of a page
or QTextBrowser standing in for a CSS engine. Callback limitations are visible:
background repetition, per-corner CSS border radii, non-solid borders, text-transform
capitalize and named-anchor scrolling are not implemented. The admitted stylesheet
property grammar intentionally excludes features without corresponding callbacks.

| Input/resource | Admission/budget |
|---|---|
| HTML | nonempty,32KiB, no embedded NUL,256 tags,16 nested explicit elements |
| Markup | balanced html/head/title/body/style/link,h1–h3,p,a,div,span,b,strong,i,em,ul,ol,li,img,br,hr,pre,code; malformed/unbalanced/unknown tags rejected |
| Attributes |16/tag;256 bytes/value; href/src/class/id/rel/title/lang/alt; numeric width/height≤512; style/event/unknown attrs rejected regardless whitespace |
| CSS |8KiB/resource,≤8 imports,64 rules,256 declarations; simple type/class/id/descendant/comma selectors≤128 chars; no imports/@rules, comments, escapes, generated content or URL backgrounds |
| CSS values | explicit property/value grammar in content.hpp; px geometry≤4096, percentages≤100, margins/padding≤256px, font≤96px, borders≤16px; exponent/unknown units rejected |
| Layout | completed height≤65536; normal page viewport only is rasterized, no giant full-page QImage |
| Fonts/images |≤128 live fonts,≤8 images; uncompressed Windows24-bit BMP only,40-byte DIB, positive dimensions≤512×512, encoded bytes≤1048630 |
| Process | existing XOS heap/page/4-thread ceiling; one QPA input thread; sampled pages/threads recorded, absolute allocation peak and long stress not measured |

`bad_alloc`/resource-limit exceptions become an engine error; the layout guard is
reset on every path so later valid navigation can recover. Rejected images are
omitted and logged; pages do not gain device rights. There is no complete fuzz,
security audit or resource-OOM guarantee for arbitrary hostile Web content. The
small admission subset is an engineering constraint, not a general HTML sanitizer.
UTF-8 goes through QString/FreeType/HarfBuzz with original DejaVu Sans; observed
Latin/accented Latin/Greek glyphs do not establish CJK/full Unicode/IME coverage.

## Network and future engine boundary

The UI explicitly states local preview, JavaScript off and network unavailable.
HTTP/HTTPS schemes are rejected. The separate `browser_http` module has bounded
URL/HTTP parsing and its own host/XOS process evidence; it has no NIC/service
transport and is not called by this browser. N2/B2 remain dependent on a qualified,
authenticated network service and an explicitly registered device mechanism.
TLS/CA/name/time/random validation, DNS, Internet browsing and JavaScript are
NOT_RUN/unsupported. Certificate checks must never be bypassed or silently fall
back to HTTP. A future network provider can supply bounded bytes/resources to
this same engine/container/shell; replacing the layout engine need not change
Aurora navigation or the kernel.

Evidence, measured scope and failed iterations are in
[0083](../work_log/0083_aurora_browser_offline.md).
