# Pumpkin sealed resource on the ordinary system

Baseline `a2e5cb45bda45ad97ce0399f9d687fc781585419`. The resource broker
implementation and replay fixture are at
`8ca1f1491cb08a461d9cf98ed97a80b55c5b03ea`. The
[resource contract](../contracts/pumpkin_resource_service.md) describes its
trust boundaries.

The broker opens one anonymous file on its own files session, writes a
bounded payload and seals it. It privately retains the object key, the
owner's full Pumpkin identity and the authority incarnation. Each read
consumes the existing resource dispatch decision within the same service
iteration and returns bytes. The resource's native files handle stays with
the broker. A failed publication leaves any acquired handle confined until
the broker releases it or exits.

## Exact guest replay

```sh
python3 -B scripts/build.py --output-dir build/pumpkin_resource_system
python3 -B scripts/build_pumpkin_daemon.py --resource-probe \
    --sdk build/pumpkin_resource_system/sdk --output build/pumpkin_resource_fixture
python3 -B tests/pumpkin_resource_guest.py --system build/pumpkin_resource_system \
    --fixture build/pumpkin_resource_fixture --output build/pumpkin_resource_guest
```

QEMU 11.1.2 booted the ordinary system with no Pumpkin/private-slot profile.
The test fixture was launched through xsh's existing explicit child-spawn
path on a disposable work disk. The broker verifies two real native
endpoint pairs against the PIDs it started. Clients verify their peer using
their kernel-authenticated parent binding. The fixture creates accounts with
guest entropy, passes credentials on those private endpoints, and uses
the existing login dispatcher and an explicitly volatile test store.

Each of two rounds read the exact sealed bytes as the owner. The fixture
verified empty replies for absent native grant, stale authority incarnation,
write operation, unknown object reference, another authenticated account,
that second connection copying the still-live owner's session, and the
original owner after revocation. A separate ordinary sealed file supplied a
witness handle that both clients could name but could not access through
their own native files sessions. Each round returned to
`[129711, 3, 1]` resources. The loaded files and supervisor ELFs matched
the exact baseline ordinary image byte-for-byte.

| Evidence | SHA-256 |
| --- | --- |
| Ordinary system manifest `ddac993d9adb2f08` | `a7963348daeecf68472813534ea7a6d2150526c4060d4104081d52abb386f52e` |
| Ordinary ISO | `213ed3d1ca4e34a76f9c9c93e4fd600a5b32668719d8a64f9aa1074fbe53cf0a` |
| Resource fixture | `dcfe580b55d249b5ea6f8ba0e4c61b3fd751483fea6ed655de0109c61a4279e9` |
| Source and SDK receipt | `7417bc896a2a3c7b8f68cd967f0b6f0e29b2535f9b6b654a622a65493ce6fa1a` |
| Resource guest report | `d8a213e1c7c237354a1613b3e8ac817c9dc8cdba523bebaad1691c3836ad43db` |
| Resource guest serial | `97848ace781ed9e7b3ebbd0227864c2db1fc33392e9556eb6d5f0a42b5e64b5b` |

The exact baseline also passed the sanitized ownership and publication
suite, freestanding target compile, daemon-loop, native boot-pair/lease,
and eight host generation checks. Two baseline guest rounds verified that
successful exec revoked generic endpoints and a new endpoint authenticated
the same PID. Failed exec preserved the original endpoint. The receipt for
that separate prerequisite is
`788f6ff4e35f2e2ddc543b927dbf4a09e6b2393057b0405b548ce0c5b0f72e75`.

The explicit anchored developer profile on the baseline
(`4186b1432a8a5407`) also passed initial commit/revocation, a healthy fresh
boot and rejection of the restored old disk after a seven-second paused
snapshot. Its report is
`e42269c8f6a4973b9e515301e767a0e5dae468ad2a4fa55146c81eb161a30453`.

## Production prerequisites

Normal boot currently lacks a provisioned account-generation source outside
the swappable work disk and a trusted registrar/login path to bind real users.
The anchored QEMU replay obtains its authority from the host supervisor
over exclusive COM1. Its configured test realm, credentials and launch
route are specific to the development profile.

The first deployable slice can use the same bounded broker object with a
qualified generation authority and a trusted startup grant. Bind each
client's actual generic endpoints and current Pumpkin incarnation before
resolving its object. For a separate Pumpkin daemon, add a dedicated
authenticated service-to-service channel and a one-time association to the
client's current authenticated endpoints. Pin the object through execution,
discard outstanding authorization on rebind, and require a fresh grant
after service replacement. A sync call from the main files loop would
introduce a dependency cycle when Pumpkin publishes snapshots through the
same files loop. A separate broker uses ordinary files IPC independently.

Persistent ownership of ordinary named FAT files requires backed object and
label identity beyond the lifetime of a files process. The current Mobius
session continues to launch applications through its explicit launcher
capability. A future authenticated Mobius session must establish its own
binding, and child applications obtain separate client bindings when needed.
