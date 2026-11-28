# Authenticated distribution and approved generation publication, v1

## Status and authority

This contract defines P1-D. The recovery worklog records which implementations
and guest artifacts have actually been qualified; this contract alone is not
a test result. The installer is built with `scripts/build_xypm.py` using one
explicit glibc SDK profile, verified OpenSSL build, and independent repository
bootstrap. Builds without that configuration do not expose the authenticated
commands.

The bootstrap file contains the repository identity, target profile, trusted
Ed25519 public key, key epoch, minimum sequence and maximum validity interval.
It becomes a compiled constant in the installer. The initial official identity
is `xos.official`, key epoch 1, public key
`5b7bc2a84175ac5c729013ec1bc7345b559aa42658fc65c093bc22e258292df5`.
Its raw public key SHA-256 is
`b0f1a4b64fc9e81dcf6a104d67ca7f3dd662ea993c72d6570c182ec76d316bd6`.
Only the publisher holds its private key. Packages, downloaded repository
metadata, directory names and command line strings cannot introduce a new
trusted key. Key rotation requires an independently delivered newer bootstrap;
this version does not implement an online root-delegation protocol.

Authentication and publication are separate decisions. A valid signature
identifies the publisher and the exact intended closure. It does not confer
execution, network access, account access or catalog publication authority.

For publicly delivered installer packages, the explicit `--public-artifact`
build option removes debug sections before packing. The original ELF and its
receipt remain separate. Entry, the complete program header table, mapping
properties and every mapped byte except `e_shoff`, `e_shnum` and `e_shstrndx`
must match. Those three ELF section-table fields are recorded before and after,
as are raw segment hashes; the first load segment includes them, so its raw
hash need not match. The transformed artifact receives its own build receipt
and package digest before actual guest acceptance.

## Signed bytes and bounded resolution

`release.sig` is exactly 64 raw Ed25519 signature bytes. The signature covers
`XOS-XYPM-RELEASE-V1`, one zero byte, then the exact bytes of `release.json`.
The native verifier uses OpenSSL EVP Ed25519. It neither reparses and
reserializes the signed body nor accepts a hash as publisher authentication.
`scripts/xypm_release.py` checks the repository and selected package closure,
checks the signing key against the bootstrap, and emits the signature outside
the repository input tree.

`release.json` is at most 4096 bytes and has exactly these fields:

| Field | Meaning |
| --- | --- |
| `format_version` | Integer 1 |
| `repository_id`, `target_profile` | Exact independently compiled identities |
| `key_epoch`, `sequence` | Positive bounded integers |
| `issued_at`, `expires_at` | Positive Unix seconds with a bounded increasing interval |
| `index_sha256`, `lock_sha256` | Exact index and lock bytes |
| `generation_id`, `generation_sha256` | Exact generation manifest identity and bytes |

Duplicate or additional fields, embedded public keys, noninteger numbers,
booleans in integer positions and malformed digests are rejected. The existing
P3 resolver remains bounded to 256 repository entries and 64 selected packages.
It requires exact dependency identities, deterministic dependency order and
one version per package identity. Missing dependencies, cycles and conflicting
versions are rejected before object staging.

Every selected XPK is verified through the same open package handle, including
its manifest, file lengths and payload digests. The installer also validates
the complete production generation format, object roles, native ABI identity,
SDK manifest identity, ELF mappings, SONAME dependencies and symbol versions.
A package or a neighboring manifest cannot approve itself.

## Freshness and rollback authority

The verifier reads `CLOCK_REALTIME` from the native kernel. Nonpositive or
unavailable time is rejected. Validity requires
`issued_at <= now < expires_at` and an interval no larger than the compiled
maximum. Time earlier than the protected previous successful observation is
rejected. The native clock is part of the platform trust boundary: signed
metadata does not supply or repair it, and this version does not claim a
separately authenticated remote time service.

The protected Pumpkin checkpoint binds repository SHA-256, key epoch,
sequence, last accepted Unix seconds and signed metadata SHA-256. Lower epochs
or sequences and same-sequence different metadata are rejected. Verifying the
same release is permitted; installing it again is rejected before staging.
The installer rechecks freshness after staging I/O and before publication.

Checkpoint and catalog publication form one protected versioned CAS. The CAS
compares revision, authorization epoch and catalog epoch. A normal FAT file or
the xypm package database is never the rollback authority. Recovery uses the
exact independently selected Pumpkin snapshot; stale disk bytes cannot select
an older checkpoint on their own.

## Authenticated publisher bootstrap

The trusted parent starts the actual installer child and observes its kernel
PID. The child creates a parent pair and discovers the parent rendezvous;
both pair and discovery peer must match the kernel-observed parent. The parent
checks its accepted peer against the child it just started. A local versioned
`publisher_startup` exchange passes the actual Pumpkin service identity and
then the installer session's daemon-side endpoints.

The parent, already the real registrar, asks Pumpkin to delegate publication
to that child/session. Pumpkin independently verifies the endpoint peer and
accepted transport session. A caller-provided PID or a successful parent ACK
does not grant a role. Before any staging write, the installer requires an
`ok` reply to the explicit read-only `publisher_checkpoint` operation from the
actual daemon session. A public checkpoint read is insufficient. Ordinary
clients cannot obtain publication by supplying a `verified` flag.

Publisher delegation permits checkpoint, catalog staging and generation
admission operations. It does not grant account/application writes or further
delegation. Disconnect or endpoint death removes the session binding. The
parent keeps its ACK endpoint until the child has consumed it or exited.

## Immutable staging and publication

The authenticated publisher writes only new content-addressed object paths
`/usr/lib/xos/objects/<sha256>.elf` and new generation manifest paths
`/usr/lib/xos/generations/<id>.bin`. The interpreter retains its fixed ABI
pathname and can be reused only when its exact bytes match. Existing paths are
not overwritten or removed. New objects use exclusive creation; an existing
object is accepted only after hashing the opened object and pinning it.

This path uses the existing public FAT write mechanism. It is not a new scoped
kernel write grant. The publisher role authorizes the protected root update;
it does not make neighboring FAT metadata authoritative. Runtime launch
independently pins and verifies every approved object again, including after
concurrent public-disk changes.

Every object and the manifest must complete write, close, sync and pinned
readback before the single catalog CAS. Pins are retained through that CAS.
The candidate appends to the bounded four-root approved catalog, preserves
revoked bits, advances catalog epoch and selects the new root atomically with
its checkpoint. CAS failure leaves the old selected root; no separate
uncheckpointed activation is exposed.

A transport timeout after submission, unknown durable publication outcome or
unconfirmed pin cleanup quarantines the controller and returns exit code 75.
The controller must not retry an uncertain side effect. A known rejection
returns 3; confirmed installation returns 0. Partially staged immutable files
can remain after interruption, but they have no approved root and are not
automatically executed. P2 maintenance install/upgrade/recovery behavior is
unchanged.

## Evidence and scope

The host suite executes the production verifier with real EVP signatures and
separate test keys. The guest suite uses the actual target glibc/OpenSSL
installer, Files transport, authenticated registrar/publisher IPC, protected
CAS, capsule-v3 admission and two real GNU libc application generations. It
checks specific rejection diagnostics, unchanged state after rejection and
interruption, upgrade, rollback and exact application output across fresh
boots.

The dedicated guest control bridge uses an existing kernel-authenticated
sys84 pair for supervisor-to-proxy traffic. It verifies both peers and an
explicit PPC1 HELLO/ACK, then unpublishes the rendezvous. Daemon-to-proxy
storage traffic retains the existing sys81 pair. The supervisor records the
two actual successful endpoint creations; both participants validate the
kernel-reported owner and opposite peer. Participant enumeration must show no
additional legacy control channel: it does not enumerate channels where the
supervisor is only the owner. The real loader must still complete its READY/ACK
exchange using the remaining existing slots. Kernel quotas, production RPC deadlines,
admission and runtime code are unchanged by this fixture arrangement.

The isolated launch profile explicitly selects a 300-second private backing
lease with `--pumpkin-launch-probe --pumpkin-launch-storage-lease`, together
with the anchored provisioning profile. Its profile and duration are included
in the system build identity. The ordinary private-storage lease remains 30
seconds, the existing desktop lease remains separate, each provisioning/Files
exchange remains bounded to 5 seconds, and installer staging has one 120-second
absolute deadline. A backing lease is a service lifetime, not an extension of
an already submitted request. The installer does not renew it or replay a
failed publication. Deployment must select an authorized backing lifetime
that covers the intended bounded operation.

The COM1 developer authority used by these integration tests is explicitly
distinct from P1-C's production independent-UID generation provider. No test
here equates same-UID host isolation, normal sync, a process stop, or an ACK
fault with arbitrary physical power-loss resistance.
