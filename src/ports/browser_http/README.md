# Bounded URL / HTTP parser preparation

This original Apache-2.0 component is deliberately independent of Qt, liteHTML,
devices and sockets. It allocates no heap and grants no authority. It is preparatory
work for a future controlled HTTP loader, **not an implemented network client**.
The Aurora browser continues to reject network navigation until a real user-mode
network service and TCP guest gate exist.

The parser follows a restricted reading of [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986.html)
and [HTTP/1.1 framing](https://www.rfc-editor.org/rfc/rfc9112.html), consulted
2026-10-29. The code is original; no RFC implementation/source code was copied.

Supported preparation:

- `http://` ASCII DNS/IPv4 authority, explicit port1–65535, literal dot-segment
  removal, relative paths/query/fragment/network references. The fragment is never
  emitted in a request. No credentials, IPv6, IDNA or automatic scheme fallback.
  Unicode paths must already be percent encoded; encoded control bytes are refused.
- GET with Host, `Connection: close`, `Accept-Encoding: identity`. Header injection
  and caller-modified URL objects are checked again before request construction.
- HTTP/1.0 or1.1 status/headers; exactly one decimal Content-Length and an exact
  body span. Need-more and premature EOF differ; extra/pipelined bytes are refused.
  204 has no body;304 Content-Length is treated as representation metadata.
- Redirect statuses301/302/303/307/308 with at most five resolutions. HTTPS,
  transfer coding (including chunked), compression, informational responses and
  close-delimited bodies are explicitly unsupported. An HTTPS redirect fails;
  there is no downgrade or TLS bypass.

Limits: URL2048 bytes, host253/label63, headers16KiB/64 fields, body1MiB; no recursive
parsing. Invalid input never yields a partial success. The caller owns all buffers;
error output objects must be discarded. A `need_more` result is not permission to
read any exposed body fields. GCC target `-fstack-usage` reports a maximum single
parser-function frame4832 bytes in this build; this is a static compiler report,
not a measured maximum browser/process stack.

Future transport obligations remain unimplemented: authenticate controlled peers,
DNS, monotonic connection/read/total deadlines, receive and parse-call quotas,
partial TCP send, EOF/reset semantics, safe cancellation, service death and actual
request/resource cleanup. Sizes bound one parsing invocation, not an unlimited
caller loop. No automatic retry after an uncertain send. This library does not
perform requests or follow redirects on its own, execute downloads, modify files,
spawn processes, verify certificates or provide JavaScript.

Validation: [frozen parser receipts](../../../docs/reports/browser_http_20261029/README.md).
`python3 tests/browser_http_test.py` runs host ASan/UBSan; the separate
`tests/browser_http_guest.py` cross-builds and executes the same vectors in XOS.
