# Native TLS developer profile

This is a static, user-space TLS 1.3 client for the ClarkE secure transport
milestone. It uses the kernel-authenticated N2 network service and its lwIP
TCP stream. Applications supply an expected network-service PID, a resolved
IPv4 address, a DNS name for X.509 and SNI, and a DER trust anchor. TLS
authenticates the remote peer independently of native IPC authentication.

The [official Mbed TLS 4.1.1 LTS release](https://github.com/Mbed-TLS/mbedtls/releases/tag/mbedtls-4.1.1)
includes TF-PSA-Crypto 1.2.0. The source lock records the SHA-256 published
with the release and the included license files. The build elects Apache-2.0
under the upstream dual license and copies the byte-identical notices to its
output. The upstream archive is an explicit build input. It is fetched and
installed independently of the system build.

## Runtime

- The Mbed TLS BIO uses existing N2 TCP operations with one absolute
  monotonic deadline. Native IPC handles short reads and writes. Fatal
  TLS/transport errors release the connection and its authenticated session.
- The handshake requires an upstream X.509 validation result with zero
  verification flags. The DNS name is required and set before the handshake.
  Application I/O becomes available after that handshake. TLS 1.3 PSK,
  tickets, early data and the bundled server and socket adapters are disabled.
  X.509 uses Mbed TLS's built-in textual IP parser. The SDK headers expose
  address families without implementing libc `inet_pton`.
- The TF-PSA-Crypto DRBG is seeded and periodically reseeded by the upstream
  entropy-driver interface. Its XOS adapter reads the requested bytes through
  glibc `getrandom(..., 0)` and fails on an incomplete result. The kernel's
  RDRAND policy supplies the entropy. The adapter uses no persistent seed or
  file keys.
- X.509 checks use the real UTC clock through glibc
  `clock_gettime(CLOCK_REALTIME)`. Clock failure cannot become a plausible
  calendar date. The millisecond platform hook uses `CLOCK_MONOTONIC`.
- The client distinguishes authenticated TLS `close_notify` from TCP EOF.
  The controlled HTTP consumer requires an exact, bounded Content-Length
  response and verified TLS closure.

The developer profile trusts the QEMU host clock and the test root embedded in
the test ELF. Each stream is single-use. The current configuration is for
single-threaded clients because the library's PSA state is process-global.
The stream lives in user space and leaves the request protocol and its origin
policy with the application. Future command-line HTTPS clients and a ClarkE
network process can reuse the transport after qualification of their own
policy and concurrency requirements. Public trust store, production time
assurance, hardware entropy qualification, DNS integration, multithreaded
clients, and NetworkProcess integration are outside the current evidence.

## Reproduce

Use a completed static glibc SDK with verified GNU source. Run the probe
builder where its recorded GNU cross tools are available. The builder checks
the exact tool and sysroot hashes, and the XOS clock and random bridge sources.
CMake is a build-host tool. OpenSSL on the test host must support `x509
-not_before` and `-not_after` for the controlled expired certificate.

```sh
python3 -B tests/native_tls_guest.py prepare --certificates build/tls-certificates
python3 -B src/ports/native_tls/build_probe.py \
  --archive /path/to/mbedtls-4.1.1.tar.bz2 --sdk /path/to/signed-glibc-sdk-build \
  --test-root build/tls-certificates/tls_test_root.h --output build/tls-probe
XOS_LWIP_SOURCE_ARCHIVE=/path/to/lwip-2.2.1.tar.xz \
  python3 -B scripts/build.py --output-dir build/tls-system
python3 -B tests/native_tls_guest.py test --system build/tls-system \
  --probe build/tls-probe --certificates build/tls-certificates --output build/tls-guest
```

Use fresh output directories and disposable local certificates. The guest
runner binds the system, native headers, probe build receipt, program ELF,
and test trust anchor before boot. The client targets each test listener
through QEMU's loopback gateway. The peers verify SNI, fresh HTTPS data and
both directions of TLS closure, and confirm that certificate
rejections send no application request. Another VM disables RDRAND and checks
that the same program exits before `main`. The private test certificate keys
stay in the host fixture directory.
