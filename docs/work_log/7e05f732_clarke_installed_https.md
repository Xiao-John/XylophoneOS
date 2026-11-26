# ClarkE installed HTTPS navigation

The tested browser source is the published commit
`ac4f413fa898575d2ffe20c58799a7fb908dd7b4` (Git tree
`722d71dd6ebd2ad80b695ccbb31f0c50165035de`). The glibc Qt Widgets build
uses the locked Mbed TLS 4.1.1 library and a single explicit developer trust
profile. It binds `tls.xos.test:28473` to the QEMU loopback route and the
disposable DER root. The browser keeps TCP device rights in the N2 service.

The existing HTTP response reader validates the same bounded framing for HTTP
and HTTPS. HTTPS waits for certificate and hostname validation before writing
HTTP bytes and accepts the response only after receiving and sending TLS close
notifications. The origin check includes the scheme, host and port. The actual
browser shows the verified TLS status after loading a secure page. The
`xos.clarke` developer XPK includes all three locked native TLS license notices.

## Guest validation

Using the commands in the [ClarkE contract](../contracts/aurora_browser.md#controlled-https-guest-build),
the offline installer placed the verified XPK into a fresh FAT32 work disk.
QEMU 11.1.2 ran the installed `/usr/bin/clarke.elf` on system
`06608c726fa0dbc5`. The guest loaded a fresh HTTPS document, stylesheet and
bitmap, verified their response hashes, and painted matching colors and pixels.
A separate document's plaintext stylesheet was rejected. An untrusted chain
produced an unknown-CA alert before the host observed an HTTP request.
The five TLS connections had the expected SNI. The four valid exchanges closed
in both directions. Each browser exit restored the native resource baseline.

The same installed XPK also loaded a fresh numeric IPv4 plaintext HTTP control
in a separate guest boot. The browser showed its plain HTTP status, the body
hash matched, and native resources recovered. The control report SHA-256 is
`9e4379e6cb7b4b4c122dddc20ffc3f4e133a9b412bd953e0e45623e6c79f4d47`.

The host test now waits for the server to record the rejected handshake before
checking the trace. The same XPK passed all four checks in the synchronized
replay. The QEMU report SHA-256 is
`e79153b0284ebc0865f2e24ddee4e0025e3d67be32637f928e4d486852b1fe7c`.

An initial candidate used a different DNS name from the certificate's SAN.
The guest rejected it before sending HTTP. The accepted profile was rebuilt
with the certificate's actual DNS name. Host checks also passed 211 parser
cases, 4,096 malformed vectors, and the HTTP/HTTPS origin and budget checks.

| Artifact | SHA-256 |
| --- | --- |
| System ISO | `67d61c0c150200d88bb3443372ca854ed9c4df7c43302ea3552b04ba14ca3a59` |
| Browser ELF | `f2865ad3ae7e820d337d0a1ea0e7ebb62635b7cbac92e7effc12bb3ce78436ad` |
| Developer XPK | `587d54005dc7a1de30a123abb2f3cfc10c7aedf40b7173abb2354bdd0656b77a` |
| Browser build receipt | `438dfcee3fda2a46acc19b8e07d00675224f0fdf4e93a5920c831f8846cb2689` |
| Native TLS build receipt | `30821f7ebbf5fa727aaa4f89eeec3e92af7714c3df4da9a5396c73bdc781dfce` |
| QEMU report | `01e46bc637ddd0099ac5224e70a16e96fec8d2108e5a3c2dc6c9423715e521a5` |
| QEMU serial log | `c4f72454e546df2b7641b0853fd5c4ec9280789e6c2046da514d0b026d68ac5b` |
| QEMU scanout | `b3f63b89d1490f725d776b9b749d67f4b6b66d1b394220b110821ce4db3a249a` |

The qualification uses the developer clock and entropy profile. Production
trust, DNS, asynchronous browsing and the WebKit NetworkProcess remain open.
