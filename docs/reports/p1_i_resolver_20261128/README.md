# P1-I1 ordered resolver qualification

The production service passed the controlled two-resolver guest subset on
system `54fbff945aa81345`, using its matching native SDK and a newly compiled
caller. The recorded QEMU version is 11.1.3. No host libc DNS lookup, host DNS
daemon or socket mock supplied the target result.

| Requirement | Actual observation |
| --- | --- |
| Ordered failover | Silent `10.0.2.2` followed by answering `10.0.2.3`; packet capture and independently recorded destination counts agree |
| One deadline | Both resolvers were contacted; the 9-second caller deadline expired at 9.03 seconds of guest monotonic time |
| Positive TTL | Immediate normalized-name cache hit retained the exact original expiry; a 2-second TTL then required a different wire answer |
| Epoch retirement | An unexpired 120-second cached answer was replaced after controller epochs 1 → 2 → 3 |
| Cancellation | A deliberately injected late answer could not complete or seed the replacement ticket; its source port and transaction ID changed |
| Foreign ownership | Another process could neither collect nor cancel the first owner's ticket |
| Quotas | A second ticket in one session was rejected; four owners exhausted the application session bound |
| Owner exit | Killing one ticket owner admitted a replacement; all remaining owners were then killed and waited |
| Recovery | Service stop restored `[free pages, tasks, completions]` exactly to `[129769, 2, 0]` |

The first fallback answer took 7.84 seconds, the post-TTL query 7.99 seconds,
and the post-epoch query 7.61 seconds. These are observations of this bounded
lwIP retry schedule, not a latency promise for an arbitrary caller deadline.
One ICMP port-unreachable response to the injected cancelled DNS packet was
observed and its quoted IPv4/UDP header was checked against that exact packet.

The production DHCP/lwIP host suite passed 19 cases under ASan and UBSan,
including two option-6 resolvers and reversed-order renewal. LeakSanitizer was
disabled because this executor runs under ptrace; no LSan pass is claimed.
The profile test passed four compatibility cases and seventeen rejection cases.

## Evidence and reproduction

`guest.json`, `guest_serial.log.gz` and `network.pcap` contain the successful guest
result, process observations and independent wire transcript. `host.json` and
`profile.log` contain the supplementary host results. `system.json` is the
path-sanitized source/artifact binding of the actual system. `raw_receipts.json`
records the original private receipt hashes; Serial logs retain their original CR/LF bytes inside gzip; only host paths were substituted
in the public derivatives. `manifest.json` hashes every public file directly.

Rebuild with the locked lwIP 2.2.1 archive and this explicit installation input:

```json
{"revision":3,"pci_instance":41,"resolvers":["10.0.2.2","10.0.2.3"],"egress":[]}
```

Then run `tests/net_multi_resolver_guest.py --system` against that build and a
fresh output directory. The runner checks all current source and system
artifact hashes and compiles the native probe from that same exported SDK.
It rejects mixed SDK/image/source inputs.

## Retained failures and scope

Four prior failures are retained. The first runner attempted NIC warmup before
stopping the installation's already running service. The second expected
`name_connect` to report the service-session quota synchronously, although
transport connection precedes service admission. The third rejected the legal
ICMP response to the cancelled query. The fourth closed QEMU before stopping
the packet peer, causing a teardown EOF to be misclassified as a peer failure.
These test corrections did not change DNS production behavior. The final run
completed every original requirement, including quotas and resource recovery.

This evidence qualifies the ordered resolver subset. It does not qualify a
physical NIC, link-loss recovery, PCI device reappearance, recursive DNS,
TCP DNS fallback, IPv6, or a complete POSIX networking implementation. Link and
device qualification are separate P1-I2 work. The Net2 page behavior present
in the source baseline was not exercised by this native DNS probe and is not
qualified by this report.
