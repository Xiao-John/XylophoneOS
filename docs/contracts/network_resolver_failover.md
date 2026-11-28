# Controlled resolver failover (P1-I1)

The installed network authority may select an ordered pair of DNS endpoints.
The production Net2 service uses the pinned and patched lwIP resolver. This
module retains the existing IN A ticket protocol, absolute deadlines, source
validation, bounded tables, cancellation and configuration epochs.

## Installation and compatibility

Static installation profile revisions 1 and 2 retain their exact schemas and
single `resolver` field. Revision 3 has exactly `revision`, `pci_instance`,
`resolvers` and `egress`. `resolvers` is an ordered array of one or two distinct,
canonical IPv4 peers on the admitted static `10.0.2.0/24` subnet; the local,
network and broadcast addresses are rejected. Empty lists, duplicates, extra
fields, duplicate JSON keys and profiles over 4096 bytes are rejected before
building. The raw profile hash and ordered addresses are bound into the system
manifest. The profile is trusted installation input, never DNS response data.

DHCP retains its existing approved policy and option 6 parser. A reply may
select up to two distinct resolvers already authorized by that installation's
allowlist. The published primary and secondary are replaced together only
after an approved configuration and ACD. A change to either endpoint or their
order changes the lease configuration epoch, retiring old application sessions,
connections, tickets and cached answers. Lease retirement clears both servers.

No syscall, Net2 opcode, configuration revision or wire structure is added.
`config_snapshot.resolver` and `lease_snapshot.resolver` retain the primary
address meaning; the complete installed ordered list is in the profile receipt.
Old clients continue using the same opaque DNS tickets and error values.
Rolling back selects an old revision 1/2 profile and matching service image;
an old builder rejects revision 3 instead of dropping the secondary silently.

## Deadline, result and lifetime rules

Every DNS start has one absolute monotonic deadline, bounded by the existing
30 second service ticket limit. lwIP first contacts the primary. Its existing
bounded retry schedule can advance to the secondary after primary timeout.
This transition neither allocates another client ticket nor changes the
original ticket deadline. The service cancels the resolver subscription when
that deadline expires. A short caller budget may expire before failover; it
does not imply a minimum time allocated separately to each server.

An authenticated, syntactically valid DNS error response is a result of that
query, not permission to search arbitrary endpoints. The current fallback is
for timeout, not recursive routing, TCP DNS fallback or automatic probing of
unapproved servers. Only the active resolver's address, source port 53, local
destination, transaction ID and exact normalized question may complete a query.
An old primary reply after changing to the secondary cannot complete it.

Positive cache expiry is the monotonic receive timestamp plus the accepted
TTL, with the existing overflow bounds. Cache hits retain the original expiry;
they do not refresh it. Expired entries require new wire input. Configuration
changes reset the entire resolver table and both server slots. A ticket's
owner generation and epoch still have to match before publishing its result.

The existing one ticket per application session and four application session
limits apply across both servers. Duplicate normalized questions may share
wire work while retaining separate owner tickets. Cancel, owner exit, session
revocation and epoch retirement remove the corresponding subscription. A late
reply cannot resurrect a cancelled ticket or populate a replacement query's
result. DNS success grants no socket, network egress or execution authority.

## Qualification

`tests/net_static_profile.py` checks old-schema compatibility and rejection
boundaries. The production DHCP/lwIP host fixture includes dual option 6
configuration and endpoint-order epoch retirement under ASan/UBSan.

`tests/net_multi_resolver_guest.py` runs the production service on a real guest
NIC with two controlled Ethernet/IP/UDP DNS peers. It binds source, SDK, image,
native caller, packet capture and serial output. The cases cover primary
timeout and secondary answer, cache hit and TTL expiry, an unexpired answer
retired by epoch change, a single deadline spanning both resolvers, cancellation
with a deliberately late reply, foreign ticket denial, owner/global quotas,
owner termination, replacement admission and exact guest resource recovery.

This document describes implemented behavior and the qualification procedure.
Pass/fail observations belong to the accompanying report; a test definition is
not evidence that it ran. Link loss, device reappearance and physical NIC
qualification remain separate P1-I modules.
