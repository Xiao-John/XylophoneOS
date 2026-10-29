# 0084 Network foundation — real VirtIO-Net Ethernet and pinned lwIP target probe

2026-10-29. **N1 PASSED in the restricted trusted boot diagnostic scope.** This is
not an installed network service or guest TCP/IP/HTTP/browser-network completion.
N2 is BLOCKED on the separate lawful user-device bridge/ABI prerequisite; DNS,
HTTPS/TLS and internet browsing are NOT_RUN.

## Scope, ownership and architecture

Independent branch `codex/browser-net-n1`, worktree `XylophoneOS-browser-net`, based
on newly fetched upstream main39083f9968d84b5679c86a74a6c8394033c0d915. PR16 is merged;
PR17 was still open and its fault-bundle changes are not depended on or modified.
Existing seven worktrees and their sources/builds were preserved. This task owns
network platform source, minimal PC IRQ gates/dispatch, opt-in boot diagnostics,
its build profile/tests/contracts and the isolated lwIP compile probe. Separate
browser and ABI-registration branches own their changes. No merge/main push/Release,
proxy/TUN/Clash change, other-project cleanup or old frozen-report rewrite.

PCI discovery/BAR validation/UC mappings are reused unchanged from the accepted GPU
foundation. GPU's single synchronous fenced queue is not reused as network RX/TX.
Net creates independent length16 asynchronous rings,34 allocated owned DMA pages,
validated MAC/modern features and real PCI INTx route. Minimal IRQ5/9/10/11 gates
acknowledge the actual device and PIC; the qualified route is a previously masked
boot-diagnostic PCI line with level ELCR. RX bounded copy/repost, TX all-frame enqueue,
AGAIN backpressure, malformed frame rejection, pending overflow, metadata fail-closed,
PIT/INTx `HLT` waits and reset-before-release are implemented. No idle network polling.
The existing boot UART monitor still polls; no whole-system idle claim.

Hardware validation/IRQ/isolation belong to the platform mechanism; TCP/DNS/HTTP
policy remains for userspace. No new syscall, user DMA/BAR map, SDK capability,
program-name privilege or business-protocol parsing in scheduler/IPC. Actual existing
user mechanisms cannot reach NIC DMA; the ordinary MMIO/PCI IO probes fault and
reclaim, rather than serving as an implicit grant. Device/service contract and
C20–C26 necessity/scope/owner/exit registration: [virtio_net](../contracts/virtio_net.md).
The separate [device ABI claim PR18](https://github.com/Xiao-John/XylophoneOS/pull/18)
remains a proposal until reviewed/merged; this branch
never defines or invokes undeclared syscall112.

## Frozen implementation and real guest evidence

[qualification.json](../reports/virtio_net_n1_20261029/qualification.json) binds the
source manifest, tools, system/SDK/image, raw host Ethernet bytes, guest logs, QEMU
command/PCI query and SHA256. Normal build67883ca24e9dcdae:

- image `build/network/qualified_system/xos.img`, SHA256
  `f019c215cd7cec00d3a5f5bbdbe91f511d0c76325c9633c7baa5eecfda721d61`.
- QEMU11.1.2 / pc-i440fx-10.0 / TCG / qemu64,+rdrand / one CPU /512MiB.
  Default launcher still `-nic none`; only this runner explicitly adds modern
  VirtIO-Net and an isolated loopback socket carrying raw Ethernet. That host
  transport is **not guest TCP/IP** and no internet service is contacted.
- Required VERSION_1, MAC, MRG_RXBUF. RX buffers4096, MTU1500, one descriptor per
  supported frame; multi-buffer jumbo fails closed. No mergeable-jumbo reassembly,
  checksum/segmentation offload, packed/event-index/indirect/control/MQ support.
  Actual first noMRG zero-header failure is preserved, not relabeled passed.

Nine initial network gates pass; the same-boot Qt fault gate below adds a tenth:

| Gate | Real observation |
|---|---|
| echo | Two init/reset cycles,32 guest TX frames host receives byte-exact; per cycle16 host echoes with varied60..382/1514-byte lengths guest verifies fully;16 actual TX completions; live INTx;34 DMA pages reclaimed |
| timeout | Host receives16 actual frames but sends no reply; guest HLT wait reaches PIT deadline with RX0/TX16, then reset/reclaim |
| overflow | Host sends8 extra valid frames after16 echoes; bounded pending queue keeps16 and counts exactly8 whole-frame drops |
| jumbo | Host sends a real5000-byte frame; actual merged receive metadata fails device closed, all34 DMA pages reclaimed |
| absent | No NIC, explicit diagnostic unavailable, unchanged old system reaches Xshell |
| echo_gpu | Actual VirtIO-GPU-only display plus net, two real frame/reset cycles; no VBE display fallback hidden as GPU |
| echo_isolation | After NIC mapping and two frame cycles, ordinary ELF store to0x32000000 faults14 and OUT0xcf8 faults13; exact resource tuple(130280,2,0) after each; file sync succeeds |
| quota | Separate build --net-dma-page-limit 3 cannot initialize and still reaches Xshell |
| quota_reclaim | Three partial-allocation failures: free pages130215→130214→130214→130214; first mapping consumes one infrastructure page table; no accumulating DMA leak |

TX queue fills with16 outstanding slots while interrupts are disabled; the17th
returns-11, invalid lengths13/1515 return-22 without submission. IRQ completion then
returns slots. Short10-byte/over-MTU1515-byte host packets are genuinely received
and rejected (two per echo cycle). Standard successful reset returns34 pages to the
allocator; repeated init/reset returns to the same baseline. The5000-byte path
proves posted RX reclamation and device fail-closed; naturally wedged reset timeout,
malicious used-ID metadata injection and forced outstanding-TX reset remain NOT_RUN.

The ordinary fault ELF source/hash and freshly cross-linked ELF hash are in the
report; a fault's existence is not a production network bridge. Large images/ELFs
remain local private build products; source, manifests and compact raw evidence
are committed. Raw PPM/screenshots for unaffected Qt are in the separate regression
receipts supplied below; packet correctness is verified from bytes, not a screenshot.

## Same-boot fault containment and affected regression

The tenth network gate sends the actual5000-byte jumbo, observes device fail-closed
and34-page reclamation, then enters userspace in that **same boot**. The real QtGui
pixel fixture opens through Display Service, QMP captures its scanout, a real PS/2
Escape closes it, and service shutdown returns exact resources. Guest QImage and
actual QEMU screenshot match all1,440,000 RGB bytes. File sync and ordinary MMIO/PCI
IO denial probes then pass with exact process-resource return. Source runner and
transparent adapter hashes are frozen under gates/jumbo_qt; no host drawing or
synthetic application callback. [Actual screenshot](../reports/virtio_net_n1_20261029/gates/jumbo_qt/after-network-fault.png).

The coordinating agent independently ran **21 affected suites**, all PASSED against
the exact same build67883ca24e9dcdae and verified current SDK/runtime inputs:
E04 loader13 checks; VBE G0219; thread core/pthread/C++15/10/10; file8/persist4;
QtCore9 suites; QtGui pixel/input/lifecycle3; Widgets interactive/lifecycle2.
[Full matrix](../reports/virtio_net_n1_20261029/regressions/affected_regression/report.json)
retains original/executed runner hashes, reports, raw compressed serial/QEMU/host
logs and actual screenshots. This is targeted regression, not whole-system,
absolute-memory, long-stress, SMP or static-release requalification.

Initial broad-run host setup leaked target COMPILER_PATH into later host clang
links; it was restored after target probe compilation. Initial E04 boot without a
work disk reached the existing maintenance guard, then was rerun with an explicit
disposable512MiB FAT32 disk. Both failed setups/raw logs are preserved; neither is
counted as a guest qualification failure or a pass. No production behavior was
changed to make a setup pass.

## lwIP source/target status

Official lwIP2.2.1 tag STABLE-2_2_1_RELEASE peeled commit
77dcd25a72509eb83f72b033d219b1d40cd8eb95, all upstream src/COPYING SHA256 locked;
no upstream patches. Original BSD-3-Clause COPYING and component/material hash are
preserved. [Port instructions](../../src/ports/lwip/README.md) describe actual sources,
compile options and missing integration. Full real core/IPv4/Ethernet target archive
cross-compiles against the same qualified SDK; commands/archive hash/unresolved
symbol report are frozen in inputs/lwip_receipt.json. No host library substitutes.

NO_SYS single userspace loop; no socket/netconn; heap128KiB,32×1536 pbuf pool,
8TCP/8UDP PCBs,4listeners,32segments,4MSS TCP send/window. DHCP/DNS compile, while
IPv6/IP fragmentation/reassembly are disabled. sys_now/random hook bindings remain
unresolved until the actual service is implemented; no fake clock/random/network
stub. **CROSS_COMPILE_PASSED** does not claim any ARP/IP/UDP/TCP/ICMP/DHCP/DNS guest
packet, sockets or browser HTTP qualification. N2 cannot lawfully be connected to
hardware until the device authority/copy/wait/lifecycle registration is accepted.

## Verification, failures and reproduction

All final source hashes were rechecked against manifest after the gates. License
material/SDK copy check passes7 materials; not a member-level/static-distribution
legal audit. ABI table remains66 allocated syscalls; ABI/doc consistency passes.
Meaningful failed compiler, noMRG, QEMU relocation and fixture attempts are retained
in exploratory_failures, with the explicit limit that early exploratory full source
manifests/images were not frozen. No failed attempt is counted as qualification.

```sh
python3 scripts/build.py --output-dir build/network/NEW_SYSTEM
python3 scripts/build.py --output-dir build/network/NEW_QUOTA --net-dma-page-limit 3
QEMU="$QEMU_BIN" python3 tests/virtio_net_acceptance.py \
  --system build/network/NEW_SYSTEM --output build/network/NEW_ECHO --mode echo
```

Use `--mode timeout|overflow|jumbo|absent` for the distinct gates; quota mode takes
the quota system. `--gpu` adds an actual GPU-only backend; `--access-payload` takes
the source-matched cross-linked isolation ELF and uses a dedicated512MiB sparse
FAT test disk. All output directories must be new. The standalone supplemental
quota_reclamation.py is retained with its exact final source/configuration.

## Remaining executable work

Review/merge the separate minimal network-device authority/ABI claim; implement
its rights, copy, wait and lifecycle with actual client-denial/grant/exit probes,
then bind a userspace NO_SYS lwIP service and run controlled ARP/IPv4/UDP/TCP/ICMP,
static config or DHCP and DNS tests. Only after accepted TCP/client semantics should
the browser enable controlled HTTP. TLS needs its own real entropy/time/CA/chain/
hostname/validity/fail-closed gate. No POSIX socket, HTTPS, JavaScript or complete
modern-browser claim follows from this Ethernet milestone.
