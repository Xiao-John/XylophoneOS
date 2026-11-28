# P0-N1 final native readiness and half-close replay

The current public implementation was rebuilt from `7d4489df05b5e6bff57794773d3f4a1727d8cc57` using the
verified Preview 2 tools and the pinned lwIP 2.2.1 source. This run used a distinct
manual-start network image and its matching native SDK; it did not borrow the
DHCP or automatic static-profile image used for the other network modules.

All 12 guest checks passed. They exercised fresh HTTP/UDP challenges, orderly TCP
close, TCP write half-close, four concurrent independent applications, wrong
service identity, a refused connection, complete service restart, and two
controlled receive-window/close cases. The half-close peer observed client EOF
before returning its fresh challenge. The independent window peer verified a
close with at least 4096 bytes still unsent behind an advertised zero window and
a separate close after all 8192 bytes had been acknowledged. Both produced the
expected FIN and exact bytes. Every exchange and service lifecycle passed its
resource-restoration assertion.

Host checks compiled actual production lwIP and passed 32 scenarios plus two
production-service-loop cases with ASan/UBSan. The native transport/HTTP regression
and freestanding link without libc also passed. LeakSanitizer was not run.
The image's 10-item license-material/SDK-copy check had no open item.

## Reproduction

Set `XOS_LWIP_SOURCE_ARCHIVE` to the locked archive and run inside the Preview 2
ordinary launcher at the qualified source. Do not add an automatic network
profile to this manual-start configuration.

```sh
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_service_host.py --sanitize --output build/n1-host
ASAN_OPTIONS=detect_leaks=0 python3 tests/net_transport_host.py --sanitize --output build/n1-transport-host
python3 scripts/build.py --output-dir build/n1-system --quiet-demos-on-launch
python3 scripts/build_net_transport_probe.py --sdk build/n1-system/sdk --output build/n1-probe
python3 tests/net_transport_guest.py --system build/n1-system --payload build/n1-probe/net_transport_probe.elf --output build/n1-guest --serial-only
python3 scripts/license_audit.py --build build/n1-system
```

The result files retain case assertions and image/SDK/probe identities while raw
captures, random payloads, serial logs and host command inventories stay local.
This is a fresh replay, not publication of a previously withheld appendix.
Dash launch was not rerun in this native module; the separate public-runtime
qualification owns its shell composition. Physical NICs, packet-loss/reordering
and reset-failure quarantine remain outside this run. DNS/DHCP/TLS are qualified
by their separate named profiles, not inferred from the native transport result.
