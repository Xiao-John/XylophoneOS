# lwIP 2.2.1 XOS NO_SYS cross-build probe

This is a real target static archive build, **not** installed TCP/IP or guest
communication qualification. The network device user bridge must first be legally
registered, implemented and accepted. No TCP/IP or HTTP logic is linked into the
kernel. Socket/netconn interfaces are disabled; no fake POSIX socket function or
always-success network interface is provided.

Source: official Savannah `STABLE-2_2_1_RELEASE`, peeled commit
`77dcd25a72509eb83f72b033d219b1d40cd8eb95`. `source_lock.json` binds every upstream
`src/` file and COPYING by SHA256. Upstream source is unchanged; patches=[]; local
configuration/arch glue is Apache-2.0, upstream BSD-3-Clause COPYING is preserved.
The dependency component/material hashes are in `licenses/components.json`.

`NO_SYS=1`, single userspace event loop, not called from IRQ; therefore
`SYS_LIGHTWEIGHT_PROT=0` is deliberate single-thread ownership, not a substitute
for locks in a threaded service. IPv4/Ethernet/ARP/ICMP/UDP/TCP/DHCP/DNS are compiled;
IPv6, IP fragmentation/reassembly, socket/netconn and advanced features are disabled.
Heap128KiB; pbuf pool32×1536, 8UDP/8TCP PCBs, 4TCP listeners,32TCP segments,
TCP send/window4×1460. This bounds configured storage, not a measured memory peak.

Real `sys_now` and `xos_lwip_random` service bindings remain unresolved in the
archive. They must use XOS monotonic time and random_bytes, never a fake clock,
fixed PRNG or host network call. Before a service is accepted, define its kernel
validated identity/grant, versioned client protocol, quotas, deadlines, short
send/error/close/exit behavior, pbuf ownership and DNS/connection limits. That
integration remains BLOCKED on the public device mechanism prerequisite.

Reproduce with the pinned SDK and compiler on PATH:

```sh
git clone --depth 1 --branch STABLE-2_2_1_RELEASE \
  https://git.savannah.nongnu.org/git/lwip.git build/network/lwip-upstream
python3 src/ports/lwip/build_probe.py --source build/network/lwip-upstream \
  --sdk build/network/qualified_system/sdk --output build/network/NEW_LWIP_PROBE
```

The builder hashes sources, compiles core/IPv4/Ethernet using target GCC and the
actual SDK headers, archives objects, and records commands/hash/unresolved symbols.
Output must be new. Successful cross-build does not prove any ARP, UDP, TCP, DHCP,
DNS or browser traffic in XOS. Real host/guest Ethernet qualification belongs to
the separate VirtIO-Net report; its host socket backend framing is not guest TCP.
