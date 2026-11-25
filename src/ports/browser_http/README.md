# Bounded HTTP parsing and native transport

This original Apache-2.0 component provides an allocation-free URL/HTTP parser
and a controlled HTTP client over the authenticated `net2` user service. The
parser remains independent of Qt, devices and networking. `transport.cpp` uses
`<xos/net_transport.hpp>` and requires a connected client whose service PID came
from a trusted launcher. The native path introduces no POSIX socket, errno, FD,
pthread/TLS or libc-private interface. Aurora navigation is integrated separately.

The parser follows a restricted reading of [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986.html)
and [HTTP/1.1 framing](https://www.rfc-editor.org/rfc/rfc9112.html), consulted
2026-10-29. The code is original; no RFC implementation/source code was copied.

## Accepted parsing and framing

- `http://` ASCII DNS/IPv4 authority, explicit port1–65535, literal dot-segment
  removal, relative paths/query/fragment/network references. The transport accepts
  canonical numeric IPv4 only; DNS remains a parser input, with no resolver.
- GET with Host, `Connection: close`, `Accept-Encoding: identity`. Header injection
  and caller-modified URL objects are checked again before request construction.
- HTTP/1.0 or1.1 status/headers; exactly one decimal Content-Length and an exact
  body span. Need-more and premature EOF differ; extra/pipelined bytes are refused.
  204 has no body;304 Content-Length is treated as representation metadata.
- Redirect statuses301/302/303/307/308 with at most five resolutions. Transport
  redirects must retain the original numeric address and port. A changed origin
  is denied before a connection is opened. `max_redirects=0` returns the first
  complete response and its status without following Location.

Limits: URL2048 bytes, host253/label63, headers16KiB/64 fields, body1MiB; no recursive
parsing. The caller supplies the buffer and can impose a smaller total capacity.
`fetch(client, input, buffer, capacity, deadline, response, final_url, max_redirects)`
returns exact wire bytes in that buffer; the successful response's body_offset and
body_length select its complete body. `final_url` supplies the base for relative
resources. Error outputs are empty. The existing pure parser's `need_more` result
requires callers to wait before consuming a body.

## Native transport behavior

The caller supplies one absolute sys46 monotonic deadline for connection, partial
writes, reads, EOF, closes and all followed redirects. The SDK bounds each request
to30 seconds, validates both IPC peers and operation-specific replies, and closes
the session on an uncertain delivery timeout. Only confirmed would_block replies
are retried. TCP may return short counts; UDP uses separate methods preserving
message boundaries and empty datagrams.

HTTP scans new header bytes once and parses complete headers and EOF. One-byte
fragments therefore cannot cause repeated whole-header parsing. Body reads count
bytes against the declared length, then require EOF; an extra-byte probe detects
trailing data even when the response fills the caller's buffer. Errors cancel the
connection; failed cancellation closes the IPC session for server-side cleanup.
No automatic retry follows an uncertain send.

HTTPS, TLS, DNS resolution, DHCP, credentials, IPv6, transfer coding (including
chunked), compression, informational responses and close-delimited bodies remain
unsupported. This component does not execute downloads, modify files, spawn
processes or provide JavaScript. Browsers remain responsible for navigation and
aggregate resource policy; the separate Aurora integration uses no redirects and
a shared navigation deadline/request/byte budget.

## Validation and guest handoff

Historical parser receipts remain at
[the frozen parser report](../../../docs/reports/browser_http_20261029/README.md).
`python3 tests/browser_http_test.py` runs the existing parser ASan/UBSan vectors.
`python3 tests/net_transport_host.py --sanitize` exercises the actual SDK and HTTP
code against a controlled IPC boundary, strict-compiles the native guest probe,
and checks a host freestanding link with no libc. The host runner records source
hashes when `--output build/<directory>` is supplied. LSan is disabled in the
ptrace execution environment; ASan and UBSan fail on any diagnostic.

For the real guest challenge, build a matching N2-enabled system/SDK with the locked
lwIP archive, then run:

```sh
python3 scripts/build_net_transport_probe.py --sdk build/net_n3_system/sdk --output build/net_n3_probe
python3 tests/net_transport_guest.py --system build/net_n3_system --payload build/net_n3_probe/net_transport_probe.elf --output build/net_n3_guest
```

The guest runner verifies source/SDK/ELF/image hashes, native service identity,
fresh host HTTP201/UDP challenges and exact32-byte replies, closes, rejection,
restart and resource recovery. Optional `--dash <matched_elf> --dash-sha256 <hash>`
also exercises ordinary dash spawn. The native probe uses `crt0.o`, so dash's
script invokes it as a command and preserves its exit status; it does not request
exec image replacement. Full fixed-toolchain linking and guest execution require
follow-up in an equipped environment; see the
[N3 work log](../../../docs/work_log/e8f504b1_n3_native_tcp_udp_and_http_clients.md).
