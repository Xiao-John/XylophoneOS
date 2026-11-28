# Installed DHCP/TLS dynamic GNU composition

This named configuration composes the existing [public GNU startup
closure](public_dynamic_runtime_v1.md), [sealed DHCP installation
policy](dhcp_service_profile.md) and [pinned TLS trust
snapshots](tls_trust_store.md). It allocates no syscall, IPC operation, wire
layout or dynamic-startup ABI. Qualification belongs to the exact build and
installation receipts; a successful component build does not qualify the
combination.

## Selected installation

`p1_k4_installed_dhcp_tls_v1` uses the supported ordinary boot ISO plus a
persistent FAT disk. The ISO contains the ordinary Xsh supervisor and the
compiler-sealed DHCP/bootstrap policy. An offline XPK transaction installs the
approved native controller, GNU PIE, bootstrap, GNU interpreter/libc, generation
record, two explicit trust snapshots, deployment record and license materials.
The package database owns every payload file. No guest test imports executable
or trust files into the running installation.

This is ISO boot with an installed data/application disk. It does not introduce
BIOS hard-disk boot or assert that the existing generic default image enables
networking. The named build automatically starts its selected network service
when ordinary Xsh starts. The first application on each cold boot must succeed
without `net-probe`, `net-start`, a static fallback or a runtime configuration
override. Explicit service control is used only for the later fault/restart
case.

The package's dedicated profile binds the parent C SDK profile, complete C SDK
manifest/tree anchors, native SDK manifest/tree anchors, system/ISO,
compiler-sealed network input, explicitly frozen public GNU runtime, application,
controller and approved generation. The parent C SDK and its profile are not
rewritten. The package profile is a private named composition; it does not
relabel its C SDK as a generally qualified dynamic application SDK.

## Network and trust selection

The sealed fixture uses VirtIO instance 41, subnet `10.0.2.0/24`, address range
`.15`–`.16`, server/gateway/resolver `.2`, a 120-second maximum lease and a
60-second acquisition budget. Application egress permits only TCP to
`10.0.2.2:443`; DHCP and DNS remain service-owned control traffic. The independent
peer offers 18-second leases with T1=6 and T2=12 seconds so renewal and expiry
can be exercised without changing the production clock or lease machinery.

The caller receives the supervisor-selected service PID explicitly and verifies
both IPC endpoint peers through the native SDK. Its read-only lease query binds
the configuration epoch, tuple, issuer and absolute times. A service name or DNS
answer does not grant a replacement PID or expand the egress rule. Retired
requests fail; application I/O is not replayed across a new service or lease.
Net2 retains its one-session-per-process rule. The renewal check receives the
fresh response on the original TLS stream after the peer's DHCP ACK, then reads
the same epoch and extended expiry through that very session before closing it.
It does not open a competing session during TLS I/O.

`net2::client::lease_status(deadline, snapshot)` is an additive forwarding method
for existing operation 18 on the authenticated session. The additive
`native_tls::stream::lease_status(snapshot)` uses that method with the stream's
original absolute deadline. It returns a Net2 status, clears the output and
returns `closed` before a verified handshake or after observed peer close/finish; a
failed live query retires the stream without reconnecting or replaying I/O.
There is no new wire operation, layout, privilege or deadline extension.

Expiry injection begins only after the independent peer has decrypted the
fresh TLS request. Until then it continues normal DHCP replies, allowing GNU
loading and handshake to take time. After receiving the peer's ready response,
the caller reads the current lease on the same TLS session and binds its
bounded-failure assertion to that exact absolute expiry.

Two disposable test root generations and their complete SHA-256 pins are
compiled into the approved application. The corresponding snapshots are XPK
owned files under `/usr/share/xos/p1_k4`. A generation-2 pin applied to the
generation-1 file must fail before creating a network connection. Selecting the
explicit generation-2 file/pin authorizes its own new connection. This is an
explicit application selection, not a mutable global trust service or automatic
CA update policy. Private CA/server keys remain host test fixtures.

## GNU and TLS execution

The program is an actual GNU PIE loaded by the public controller and GNU
interpreter. It checks a constructor's initial TLS, the main thread's TLS value
and errno semantics. This C-only approved closure has no `libgcc_s` unwinder;
the existing GNU contract therefore returns `ENOTSUP` from `pthread_create`.
The fixture checks that denial explicitly. It does not claim worker creation,
cross-thread TLS isolation or C++ standard-library support. The named package
profile excludes `threads` and `cxx_runtime`, while retaining the complete,
separately verified parent SDK binding as provenance. TLS runs in the main
thread, preserving the existing single-threaded Mbed TLS/PSA boundary.

The Mbed TLS archive is the existing locked 4.1.1 source. Its libraries and native
TLS adaptation are rebuilt as PIC against the selected GNU headers and native
SDK. The application uses shared GNU libc and authenticated PIC CRT objects;
it does not link another libc archive or mix a threading/newlib CRT. No C++
standard library is needed by this restricted C++ adaptation.

The runtime and consumer may have separately frozen sources. The package builder
requires an explicit runtime Git revision, verifies every recorded recipe/port/
native input against that revision and every native snapshot/artifact byte, then
matches the 18 actual native dependency files to the 18 linked archive members.
Every actually compiled native input and public startup ABI header must also
match the consumer. Only the explicitly reviewed, uncompiled `net_transport.hpp`
convenience-method addition may differ in this configuration. The original
runtime identity remains unchanged; this does not assert it was rebuilt from
the newer consumer tree. The resulting proof is part of the installed profile.

The independent peer parses DHCP, ARP, DNS and TCP wire packets from QEMU and
uses OpenSSL MemoryBIO for TLS 1.3. Each application request carries a fresh
scenario nonce, verified after peer decryption. Ordinary successful cases also
require verified bidirectional TLS close notifications.

## Acceptance and limits

The runner first cold-boots the selected installation twice, verifies automatic
DHCP/ACD and real GNU/TLS on both boots, then exercises:

- Same-configuration renewal with a larger expiry, unchanged epoch and the
  original live TLS stream.
- Lease expiry while TLS read is pending; a bounded failure without replay,
  then a fresh lease epoch and a successful new caller.
- Orderly netd stop while a dynamic TLS caller is pending; bounded wakeup,
  confirmed device reset, explicit supervisor restart, old-PID rejection and a
  successful new-PID call.
- Installed trust pin mismatch before network use and a successful generation-2
  handshake with its separately authorized root.
- Actual netd kill while a dynamic TLS caller is pending; bounded wakeup, three
  rejected device regrants and exactly 66 retained DMA pages relative to the
  measured no-service baseline. Existing device quarantine remains enforced.
- A third cold boot of the same installed disk after that quarantine, automatic
  fresh DHCP/ACD and successful dynamic GNU/TLS without manual network startup.
- Complete caller/process/channel/connection reclamation, plus unchanged XPK-owned
  payloads and package database after all three boots and fault cases. The
  intentionally quarantined DMA is reported separately from caller resources.

The network operations use one 29-second absolute deadline per TLS stream.
Acquisition monitoring is separately bounded and read-only. An expiry result
must precede that stream deadline and fall within three seconds of its recorded
lease expiry; service-stop and service-death wakeup must each complete within
eight host seconds. The [device authorization contract](device_authorization_v1.md)
does not permit same-boot regrant after an unconfirmed reset: crash recovery here
requires a cold boot, while orderly stop/restart recovers in the same boot.

These fixtures do not qualify GNU worker threads in this C-only closure,
physical NICs, arbitrary Internet CAs, secure
hardware time/entropy, power loss, general online library loading, SMP or a
pending newer dynamic capsule ABI. Historical static/DHCP/TLS reports remain
separate from this installed dynamic composition.
