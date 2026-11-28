# P0-N3 final source replay

This is a fresh qualification of source `7d4489df05b5e6bff57794773d3f4a1727d8cc57`, using the verified
Preview 2 development environment and a newly built DHCP installation and native
SDK. It does not import the withheld final appendix of PR #418 or re-label the
historical `3699916d` network results.

The eight real-QEMU scenarios passed: renewal, expiry, NAK/configuration change,
rebinding with a new admitted issuer, malformed replies, ACD conflict,
conflict/backoff/recovery, and an explicit network-service restart. Each scenario
restored the same observed baseline: 129768 free pages, 2 tasks, 0 completions.
The independent peer supplied fresh UDP challenges and DNS replies. Expiry and
configuration replacement closed old socket/ticket authority; DNS did not grant
connection authority. The bound snapshot details and per-case results are in
`qualification.json`.

Production lwIP/DHCP/ACD passed 18 host scenarios with AddressSanitizer and
UndefinedBehaviorSanitizer. The installed DHCP JSON passed 24 rejection cases,
and egress-profile validation passed 27 cases. LeakSanitizer was not run. The
selected image passed the ABI documentation check and the 10-item license
material/SDK-copy check with no open item.

## Reproduction

Run from the qualified checkout in the Preview 2 ordinary launcher, with the
verified lwIP archive set as `XOS_LWIP_SOURCE_ARCHIVE`. `--offline` namespace
isolation is not claimed. Keep distinct new output directories.

```sh
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_dhcp_stack_host.py --sanitize --output build/n3-host
python3 tests/net_dhcp_profile.py
python3 tests/net_egress_profile.py --output build/n3-egress.json
python3 tests/net_client_host.py
python3 scripts/build.py --output-dir build/n3-system --net-dhcp-profile tests/fixtures/network/dhcp_profile.json --quiet-demos-on-launch
python3 scripts/build_net_dhcp_probe.py --sdk build/n3-system/sdk --output build/n3-probe
python3 tests/net_dhcp_guest.py --system build/n3-system --fixtures build/n3-probe --output build/n3-guest
python3 scripts/license_audit.py --build build/n3-system
```

The lock is lwIP 2.2.1, SHA-256
`83729c274c499d3348e9fbbe043a3113f3fa8953e7efddc7c21c7fcbb1f2b7b1`.
The report is a minimized result extract. It retains source, image, SDK and probe
identities and actual outcomes; it does not publish packet payloads, raw serial
output, or local host inventories. Independent packet reinspection is therefore
not established by this public extract. All original run files remain retained.

The qualification covers the explicit direct-Ethernet IPv4 profile. Default
installed networking combined with dynamic GNU applications, physical NICs,
multiple-resolver failover and IPv6 remain separate profiles. No release tag or
release asset is created by this evidence commit.
