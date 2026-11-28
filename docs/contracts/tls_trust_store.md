# Bounded TLS trust snapshots

## Authority and scope

The native TLS client accepts an immutable CA snapshot selected by a
`native_tls::trust_store_pin { generation, sha256 }`. Both fields come from the
application's trusted build or an independently authenticated deployment
configuration. They must not be read from the same untrusted directory as the
snapshot and then treated as authority. The packer's JSON receipt records
provenance; it does not authorize its own output.

This is user-space X.509 trust. It grants no native IPC handle, network service
identity or permission to connect to an address. Hostname/SNI, UTC validity,
chain validation and the independently authorized network route still apply.
The current Mbed TLS configuration is single-threaded; its process-global PSA
state and physical clock/entropy assurance retain their existing boundaries.

## Format version 1

All integer fields are little-endian. The header is exactly 32 bytes.

| Offset | Bytes | Meaning |
| --- | --- | --- |
| 0 | 8 | ASCII `XOSTRUST` |
| 8 | 4 | Format version, exactly 1 |
| 12 | 4 | Anchor count, 1 through 256 |
| 16 | 8 | Nonzero generation, exactly the caller's authorized generation |
| 24 | 8 | Reserved, exactly zero |
| 32 | variable | Repeated `u32 byte_count` followed by one DER certificate |

The entire snapshot is at most 1 MiB. Each entry is 1 through 16,384 bytes and
must contain exactly one parsed CA certificate. Its key usage must permit
certificate signing when that extension exists. Duplicate DER anchors and
trailing bytes are rejected. SHA-256 covers the complete header and every
entry. A generation is an identifier, not a self-authenticating freshness claim.

The host compiler additionally requires canonical DER round-trip equality and
orders anchors by SHA-256, giving deterministic output for reordered PEM input.
Unknown/malformed PEM blocks, duplicate anchors and a mismatched source digest
fail before publication. Comments in a PEM source do not become trust rules.

## Load, failure and lifetime

`load(bytes, size, expected)` performs bounded parsing into a temporary chain;
only a complete success publishes the anchors. `load_file(path, expected)`
reads at most 1 MiB plus one overflow-detection byte and checks stream/close
errors. File lookup does not select a trust pin. The path can therefore point
to ordinary storage without granting that storage authority over the roots.

| Result | Meaning |
| --- | --- |
| `ok` | Exact pinned bytes and a complete valid CA set are loaded |
| `invalid` | Invalid arguments, bounds, header, count or framing |
| `pin_mismatch` | Another generation or different complete file digest |
| `malformed_certificate` | Invalid DER or extra data inside an entry |
| `not_ca` | The certificate does not permit CA signing |
| `duplicate` | The same DER certificate appears twice |
| `unavailable` | File, allocation or cryptographic backend failure |
| `already_loaded` | The object is already immutable; it retains its old state |

A failed first load leaves `ready()==false` and releases the candidate chain.
A successful object cannot be reloaded. Construct and validate a separate
object for an update. `stream::connect(..., store, deadline, route)` copies the
anchors into that stream, so the caller may destroy its store without changing
an established connection. Existing streams are not retroactively revoked by a
new CA generation; policy requiring immediate revocation must close those
streams explicitly. Fatal TLS errors still discard verified peer state.

`capture_pin(output)` clears its output and returns false until the object is
ready. On success it copies the complete generation/digest identity committed
by `load`; a rejected load cannot manufacture an active identity. The optional
[`observation.hpp`](../../src/ports/native_tls/observation.hpp) bridge exposes
that identity to the [P1-A observation service](observation_service.md) for the
owner-selected store. The owner keeps the borrowed store alive and serializes
selection changes, capture and destruction. This describes the selected loaded
snapshot for new connections, not the anchors already copied into each stream.
It adds no TLS dependency to the base observation SDK. The private C++ object
layout now retains the verified digest, so rebuild the native TLS objects and
their consumers together; there is no cross-version binary-layout guarantee.

## Provisioning and rollback

1. Obtain CA source bytes through the deployment's trusted process and select
   their exact digest. The compiler never fetches or selects a source.
2. Run `scripts/package_tls_trust_store.py --pem SOURCE --source-sha256 DIGEST
   --source-url HTTPS_URL --generation N --output NEW_FILE`.
3. Review the resulting CA membership and independently authorize the output
   generation plus SHA-256 in the trusted application/deployment configuration.
4. Stage the new complete file. A caller loads it using that authorized pin and
   selects it for new connections only after `ok`.
5. An explicit rollback authorizes a previously reviewed generation/digest;
   merely placing older bytes at the current path fails the current pin.

The compiler uses an exclusive hard-link publication of a fully written,
file-fsynced temporary file. It never replaces an existing destination or a
symlink. This is a no-clobber file publication primitive, not a claim of
power-loss-safe deployment or a trusted multi-file configuration transaction.
The trusted generation selection and storage durability belong to the
deployment mechanism. Automatic CA updates, OCSP/CRL policy and rollback
freshness are not implicitly enabled.

## Public CA qualification input

The P0 parser run used curl's Mozilla conversion dated 2026-11-05, with 118
anchors. Source PEM SHA-256:
`427c064216761a1e72a8b30f0d954d08cb6e4435a82091fb865afd20c8497285`.
Compiled snapshot generation `20261105`, 127,607 bytes, SHA-256:
`8bc902a15d7d0a7d1161b26fce999fcb1e7215b2c22003bad935a0abafe8ac29`.

The [official curl CA extraction page](https://curl.se/docs/caextract.html)
identifies the converted PEM as MPL-2.0 and explains that Firefox's additional
out-of-band CA restrictions are not included. Consumers distributing this
input must preserve its source/license obligations and make their own trust
policy decision. The PEM/DER bundle is not committed or automatically selected
by this module. Its target parsing result does not qualify arbitrary Internet
sites or an equivalent browser root policy.

Controlled real TLS tests separately prove acceptance under two independently
generated roots, removal, explicitly authorized rollback, unknown roots,
wrong names, expired certificates and verified closure. The guest runner uses
fresh disposable disks and synthetic test authorities. Private fixture keys
remain local and are never part of public evidence.
