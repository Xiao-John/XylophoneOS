# P0-N2 final libc network replay

This fresh run uses source `7d4489df05b5e6bff57794773d3f4a1727d8cc57`, the verified Preview 2 host tools,
a newly built static-network image, and a separately rebuilt, upstream-signature-
verified glibc C SDK. The SDK's manifest and tree are bound in
`qualification.json`; the Preview 2 bundled newlib sysroot was not used as glibc.

All 12 real-QEMU cases passed: absent service, descriptor capacity, an
unresponsive authenticated peer bounded by the caller deadline, wrong service
identity, denied and refused connections, repeated real-peer stream/EOF paths,
and TCP write half-close across two service instances. Every case recovered its
recorded resource baseline. The no-service baseline was 129773 free pages,
2 tasks, 0 completions; each active-service baseline was 129601 pages, 3 tasks,
1 completion. These are observed values for this image, not fixed ABI promises.

The production glibc bridge host regression also passed level readiness,
absolute timeout, descriptor leases, half-close, old-server compatibility and
malformed replies. The selected static image passed its 10-item license
material/SDK-copy check with no open item.

## Reproduction

From the qualified checkout in the Preview 2 ordinary launcher, use separately
verified glibc SDK/profile inputs. The explicit static profile is revision 1,
PCI instance 41 and resolver `10.0.2.3`; the locked lwIP archive must be set as
`XOS_LWIP_SOURCE_ARCHIVE` when building the image.

```sh
python3 scripts/build.py --output-dir build/n2-system --net-static-profile "${XOS_STATIC_PROFILE}" --quiet-demos-on-launch
python3 tests/glibc_net2_socket_host.py
python3 tests/glibc_net2_tcp_guest.py --system build/n2-system --sdk "${XOS_GLIBC_SDK}" --profile "${XOS_GLIBC_PROFILE}" --output build/n2-guest
python3 scripts/license_audit.py --build build/n2-system
```

The public receipt is a minimized fresh-run result with per-case recovery and
exact source/SDK/image/probe identities. Raw serial output and local command or
tool inventories are retained locally and are not republished from the older
withheld appendix.

This qualifies the finite current poll/shutdown profile. Connected-socket
`poll(0)`, nonblocking connect, further shutdown directions and descriptor types
remain outside it. `pthread_cancel` remains `ENOTSUP`; native session abort is
not cancellation delivery. Concurrent close/revoke while a real guest is blocked
inside poll is still the explicit P1-H extension. This commit does not publish a
release or qualify a DHCP/dynamic-GNU installed combination.
