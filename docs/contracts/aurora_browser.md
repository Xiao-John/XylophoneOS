# ClarkE local HTML/CSS and controlled web prototype

2026-10-29. Application policy, not a new kernel ABI. The implementation uses the
existing Qt 6.8.3 Widgets/QPA and `libXosAurora.a`, one fullscreen native window,
and the real pinned liteHTML 0.9 layout engine with bundled Gumbo HTML parser.
The engine is independent of the local-file provider and ClarkE navigation shell.
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
reset on every path so later valid navigation can recover. Stylesheet admission
failures are reported as stylesheet failures, not as engine allocation errors: a
rejected in-block or linked stylesheet reports `Stylesheet rejected`, the
linked-stylesheet import cap reports `Stylesheet import quota exceeded`, and only
genuine allocation/resource-limit failures report
`Engine allocation or resource budget failed`. Rejected images are
omitted and logged; pages do not gain device rights. There is no complete fuzz,
security audit or resource-OOM guarantee for arbitrary hostile Web content. The
small admission subset is an engineering constraint, not a general HTML sanitizer.
UTF-8 goes through QString/FreeType/HarfBuzz with original DejaVu Sans; observed
Latin/accented Latin/Greek glyphs do not establish CJK/full Unicode/IME coverage.

## Network and future engine boundary

2026-11-25 implementation update: local mode remains the default. Explicit
`--network-service-pid <pid>` enables the native web provider, using the
authenticated [N2 service](net_service_v2.md). Obtain the PID from the trusted
supervisor's `net-start 41` output; the client verifies both IPC peers. The
browser receives bytes through the service and obtains no NIC/device rights.
The Qt target build and controlled HTTP subset have been qualified in QEMU.

Numeric IPv4 HTTP is supported within the service allowlist (currently 10.0.2.2).
An explicit glibc developer build can additionally load HTTPS at one configured
DNS origin. The build binds that origin to one IPv4 destination and DER trust
anchor. Mbed TLS validates the certificate chain and URL hostname before any
HTTP bytes are sent. A complete response also requires TLS close notification.
The shared parser accepts fully framed 2xx responses. DNS resolution, public
trust roots, JavaScript, chunked or compressed bodies and redirects remain
outside this profile.

Remote CSS/BMP resources, including their callback base, must share the document
scheme, host and port. Remote resources cannot read local files. Local documents
retain local resources. Explicit navigation, Home, history and bookmarks can
switch modes.

Each navigation shares a three-second absolute monotonic deadline starting at
its first network request, at most 17 requests, and a 2 MiB response-read budget.
Failed requests consume their reserved budget; successful reads refund unused
capacity. Existing per-resource and layout limits still apply. The provider
closes IPC after initial parsing/layout on success and failure; repaint/resize
cannot fetch new remote resources. Failed candidate loads preserve the old page.
Queued links capture resolved absolute URLs; replaced-view callbacks are disabled.

I/O runs synchronously on the GUI thread. Network waits share the deadline;
interactive cancellation and GUI responsiveness need future asynchronous work
and separate validation. Input limits govern rendering/layout CPU work.

The existing browser builder now compiles the HTTP parser and native transport,
checks its three SDK network headers match the current source revision, and
records sources and provider policy in the receipt. Rebuild matching native/
threading SDK, Qt 6.8.3 and browser together. This native interface adds no POSIX
socket or glibc dependency.

## Explicit glibc candidate build

The same ClarkE application can use the signed glibc C/C++ SDK and matching
static Qt 6.8.3 Widgets kit. The builder verifies the SDK profile, target
archives, host generators and locked liteHTML/Gumbo tree before linking. Use
the established `xos.clarke` package and `/usr/bin/clarke.elf` entry. The legacy
threading SDK build remains available for its existing package profile.

```sh
python3 src/ports/aurora_browser/glibc/build.py \
    --sdk-build "$GLIBC_SDK" --sdk-profile "$GLIBC_PROFILE" \
    --qt-build "$QT_BUILD" --qt-prefix "$QT_PREFIX" --qt-source "$QT_SOURCE" \
    --host-qt "$QT_HOST" --output build/clarke-glibc
python3 scripts/package_desktop_products.py clarke build/clarke-glibc/build/clarke.elf \
    --sdk "$GLIBC_SDK" --profile "$GLIBC_PROFILE" --output build/clarke-glibc.xpk
```

ClarkE first opens the requested local page. Only an absent public built-in
path is eligible for the packaged copy. The browser checks the actual open
regular file with `fstat` before its bounded read.

## Native HTTP guest check

After building a matching system with the pinned `XOS_LWIP_SOURCE_ARCHIVE`:

```sh
python3 tests/aurora_browser_http_guest.py --system build/network_system --payload build/browser/aurora.elf --output build/browser_http_guest
```

Use `--system-source` if the system was built from another source tree. The
runner verifies that full tree and the system artifacts against the build
manifest. The glibc ClarkE check also binds its native network headers to the
same system source digests.

The runner verifies inputs and actual GET/Host/close, checks the SHA-256 of
fresh HTML, CSS and BMP bodies, and verifies stylesheet text/background and BMP
pixels on the guest scanout. It checks resource recovery after three successful
loads, denied cross-origin and local-file stylesheets, HTTP 404 and truncated
responses, then stops the service. The same browser ELF passed the local
interactive, failure rollback, lifecycle and no-display suites.
Remote history/tab/reload, in-process budget resets, forced network service
death and GUI responsiveness during I/O still require separate qualification.
See the [implementation and qualification log](../work_log/70ac29fe_browser_native_http_provider.md).

## Controlled HTTPS guest build

Generate the disposable certificates with `tests/native_tls_guest.py prepare`
and convert their root certificate to DER. Add these options to the existing
explicit glibc candidate build command. Use an available host loopback port.

```sh
openssl x509 -in "$certificates/root.pem" -outform DER -out "$root_der"
python3 src/ports/aurora_browser/glibc/build.py --sdk-build "$sdk_build" --sdk-profile "$sdk_profile" \
  --qt-build "$qt_build" --qt-prefix "$qt_prefix" --qt-source "$qt_source" --host-qt "$host_qt" \
  --tls-origin https://tls.xos.test:28473 --tls-address 10.0.2.2 \
  --tls-archive "$mbedtls_archive" --tls-root-der "$root_der" --output build/clarke_https
```

Package the resulting ELF through `scripts/package_desktop_products.py` using
the same SDK and profile. The XPK retains the controlled trust metadata in its
receipt and includes the locked Mbed TLS, TF-PSA-Crypto and framework notices.

```sh
python3 tests/clarke_https_guest.py --system "$system" --system-source "$system_source" \
  --payload "$browser" --package "$package" --profile "$sdk_profile" \
  --certificates "$certificates" --output build/clarke_https_guest
```

The guest test loads an authenticated page, same-origin CSS and a BMP from the
installed browser. It observes rendered pixels, the verified TLS status,
rejection of a plaintext stylesheet and an untrusted certificate, bilateral
TLS close and process resource recovery.

Add `--tls-resolve-net2` to require resolution through the authenticated
N4 session. The same session opens TCP only after the resolver returns the
configured address. The URL hostname remains the TLS SNI, certificate identity
and HTTP Host. Resolver failure or a different route ends navigation. The
`pinned` address source selects the static developer HTTPS route. Numeric HTTP
uses explicit IPv4 destinations under its own policy.

For this test, build the system with `--net-dns-probe` and use a network-isolated
Linux container with `--network none --dns 127.0.0.1`. The runner starts its
private loopback DNS fixture on UDP 53 and keeps the TLS listener on the
configured high port. The container needs permission to bind its own UDP 53.
The resolver fixture and TLS listener serve only the controlled test origin.
The runner also checks a trusted certificate for another hostname and a
different DNS route without sending HTTP on either path.

On an installed static network profile, launch `clarke.elf --network` from xsh
or dash to select the supervisor-provided service binding. A shell launched
before the service restarted retains the older binding. Relaunch ClarkE from
xsh or a new dash instance to use the replacement service. The explicit
`--network-service-pid` argument remains available for developer callers.
[Network launch contract](network_n4_v1_proposal.md#22-静态安装-profile)

Historical local-provider evidence, measured scope and failed iterations are in
[0083](../work_log/0083_aurora_browser_offline.md).

Navigation loads a candidate view before replacing the current one. If parsing, stylesheet
loading or initial layout fails, the current page, scroll, address, history and active tab
remain in place; the status reports the error. This behavior is implemented
([0096](../work_log/0096_browser_review_fixes.md)) and its interactive guest regression —
failed load followed by Back/Forward, scroll restore and tab switches — has actually run
and PASSED on the 2026-10-30 combined tree
(`../reports/aurora_g3_review_20261030/combined/browser-negative/report.json`, check
`failed_engine_load_preserves_page_history_scroll_and_tabs`) and again on the post-#39
branch tree on 2026-10-31
([0148](../work_log/0148_c2_c3_debts_and_localpilot_rules.md)). Not measured here: the16-entry
per-tab history cap and the4-tab cap are implemented but no suite drives16 history
entries or4 populated tabs, and suites are not re-run after every unrelated merge.
