# P0-N4 final TLS and trust-generation replay

This is a fresh qualification from `7d4489df05b5e6bff57794773d3f4a1727d8cc57`, using the verified
Preview 2 tools, a newly built manual-start network image, a separately rebuilt
signature-verified glibc C SDK, and the locked Mbed TLS 4.1.1 archive. Every test
certificate and private peer key was generated anew for this local run. No
private key, certificate payload, packet capture or host inventory is published.

All 20 guest scenarios passed. These include valid TLS 1.3 with a fresh 32-byte
HTTP challenge and mutual close_notify, hostname/unknown-root/missing-chain/
expiry rejection, truncated TLS closure, two independently selected authorized
roots, changed and removed roots, explicit authorized rollback, corrupted and
stale store rejection, and fail-closed startup without RDRAND. Certificate-denied
paths made no application request. Every invocation restored 129506 free pages,
4 tasks and 2 completions in this selected image.

The trust parser passed its 15 target checks, and an explicitly pinned public CA
snapshot with 118 roots was parsed inside the real guest. That is a parser and
bounded-input result, not a public-Internet handshake or browser-policy result.
The real OpenSSL host packer passed 24 checks. The HTTPS transport adapter also
compiled with the same target compiler and exact glibc SDK; the full Qt consumer
was not rerun. All selected image license-material/SDK-copy checks passed.

## Reproduction

Use the qualified checkout in the Preview 2 ordinary launcher. Set the separately
verified glibc SDK and locked Mbed TLS archive explicitly. CMake 4.2.0 was checked
against its official archive checksum; OpenSSL 3.6.5 from Preview 2 supplied the
controlled certificate validity dates. `XOS_LWIP_SOURCE_ARCHIVE` selects the
unchanged locked lwIP source for the manual-start image.

```sh
python3 tests/tls_trust_store_test.py --output build/n4-host
python3 scripts/package_tls_trust_store.py --pem "${XOS_CA_PEM}" --source-sha256 427c064216761a1e72a8b30f0d954d08cb6e4435a82091fb865afd20c8497285 --source-url https://curl.se/ca/cacert.pem --generation 20261105 --output build/n4-public-ca.bin
python3 tests/native_tls_guest.py prepare --certificates build/n4-certificates --trust-store --public-trust-store build/n4-public-ca.bin
python3 src/ports/native_tls/build_probe.py --archive "${XOS_MBEDTLS_ARCHIVE}" --sdk "${XOS_GLIBC_SDK}" --test-root build/n4-certificates/tls_test_root.h --trust-fixtures build/n4-certificates/tls_trust_fixtures.hpp --output build/n4-probe
python3 scripts/build.py --output-dir build/n4-system --quiet-demos-on-launch
python3 tests/native_tls_guest.py test --system build/n4-system --probe build/n4-probe --certificates build/n4-certificates --output build/n4-guest
python3 scripts/license_audit.py --build build/n4-system
```

The Mbed TLS 4.1.1 archive SHA-256 is
`3359a349e23db3d5536fcee032ae7b2ecbfc08972fab643089b5cbf2a375c98c`.
The result extract records actual case outcomes and exact source, SDK, image,
probe and CA identities. Its raw local logs are retained separately; it does not
republish the previously withheld final appendix or claim public reinspection of
raw packets. An initial optional adapter compile used an incorrect filename and
stopped before compilation; correcting the invocation to the existing
`https_transport.cpp` produced the recorded successful object without changing
any source.

Trusted production time, hardware entropy, automatic trust updates, OCSP/CRL,
concurrent TLS callers, the complete Qt browser, and physical power-loss recovery
remain outside this explicit profile. No release is created by this evidence
commit.
