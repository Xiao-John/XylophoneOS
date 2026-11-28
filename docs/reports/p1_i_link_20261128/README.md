# P1-I2 link and controlled device reappearance qualification

The real VirtIO-net/DHCP service passed the link and controlled reappearance
subset on system **`355be568fa990b6b`**, its matching native SDK, QEMU 11.1.3
and a separately implemented Ethernet/DHCP/ARP peer. The final runner verifies
every current system source and artifact hash, the SDK tree and the separately
compiled caller receipt. No host DHCP daemon, libc DNS or socket mock supplies
the target result.

## Actual observations

| Boundary | Guest and independent wire evidence |
| --- | --- |
| Initial lease | `10.0.2.15`, epoch 2, three ACD probes and a random application challenge |
| Link loss | QMP changes actual device link status; the driver observes it; address becomes zero, reason is `link_lost`, epoch becomes 3, application session/connection/DNS identities retire |
| Down interval | No DHCP traffic during the observed three-second down interval; the host suite separately covers a 70-second interval |
| Link recovery | A new DHCP transaction acquires `10.0.2.16`, epoch 4, with a new acquisition clock and three more ACD probes |
| Old queued work | UDP payload and a TCP SYN actually wait behind unanswered ARP before loss; old connection handles and DNS ticket remain closed after recovery; an injected late ARP answer cannot release old packets |
| Orderly device retirement | Controller stops and waits for the old service before touching the PCI function; queues reset and DMA/MMIO authority retires |
| Guest ACPI eject | `device_del` is accepted, but `query-pci` still shows the old device; **the guest did not acknowledge eject** |
| Actual removal | Host QOM `realized=false` succeeds; `query-pci` confirms the old function is absent before a new `device_add` |
| Unconfigured replacement | The new function appears with no assigned BARs/IRQ; fresh `net-start 41` fails with `device_no_device` (`-7`) and publishes no service |
| Platform-prepared replacement | With vCPUs paused, the host qtest fixture assigns the old, now-unused exclusive BAR ranges and IRQ to the new function; bus mastering and memory decode remain disabled until the new grant enables them |
| Fresh service identity | Old service PID 14 is replaced by PID 17; the old caller remains alive and rejects the replacement endpoint because it does not authenticate as PID 14 |
| New network authority | The replacement performs a new DHCP transaction, three fresh ACD probes and a new random challenge; delayed ARP cannot resurrect the retired UDP/TCP queue |
| Recovery | Both the link lifecycle and final replacement stop restore `[free pages, tasks, completions]` exactly to `[129764, 2, 0]` |

The two link acquisitions used transaction IDs `3816309476` and `3769936941`.
The service lifetime before replacement used `1282775405`; its replacement
used `2288688927`. Each lifetime's nonce and independently generated response
are recorded in `guest.json` and the packet capture. These are observed values,
not fixed protocol constants. Lease diagnostic reason retains the earlier
failure history after a successful recovery; the bound state and current tuple
establish usability.

The controlled device case uses **host-prepared PCI resources**. It does not
establish a guest PCI allocator, ACPI eject support or automatic recovery from
unannounced disappearance. A link-status bit cannot identify a new device.
The native service never probes a retired MMIO mapping to guess replacement.
No physical NIC was available: physical qualification remains **not_run**.
Crash/DMA quarantine is unchanged and is not cleared by this work.
The native caller does not bind a shared readiness page or use the GNU socket
adapter. Network readiness code present in the source baseline is not qualified
by this report; P1-H has its own matching SDK and guest evidence.

## Implementation and supplementary checks

The driver negotiates VirtIO link status when offered and reads it with bounded
configuration-generation validation. The DHCP service fails closed on loss,
retires sessions, DNS and ARP/transport state, pauses acquisition while down,
and starts a new DHCP/ACD lifecycle after up. Devices without the status feature
retain the documented compatibility behavior and do not acquire a link-loss
detection claim. Static-address recovery also remains outside this subset.

The separate PCI change retires the kernel reset observer when its grant is
disabled. A subsequent grant at the same BDF must create a new mapping from
the new inspection. The production PCI implementation's host regression checks
a replacement with a different BAR, independent reset state, map failure,
unmap failure and unconfigured-device denial. Failed unmap prevents admission.
The generic device-store host suite passed eight scenarios. The actual guest
then exercised normal disable/regrant through the production backend.

The production DHCP/lwIP suite passed 21 cases under ASan and UBSan. VirtIO
queue tests passed 14 cases, and the ordinary network service suite passed
33 stack scenarios plus two production-loop scenarios. LeakSanitizer was
disabled because this executor uses ptrace; no LSan result is claimed.

## Evidence and reproduction

`guest.json`, `guest_serial.log.gz`, `network.pcap` and `qtest.log.gz` contain the
final result, actual process observations, wire transcript and host PCI access
transcript. `system.json` and `caller.json` bind the image, source, SDK and caller.
The host receipts and logs are supplementary. Public derivatives replace host
paths with explicit templates; original receipt hashes are in `raw_receipts.json`.
Compressed serial files preserve CR/LF bytes. The flat `manifest.json` hashes
every public file directly.

Use the locked lwIP archive, build the system with
`--net-dhcp-profile tests/fixtures/network/link_profile.json`, then compile
`scripts/build_net_dhcp_probe.py --sdk <system>/sdk --output <fixtures>` and run:

```sh
XOS_QMP_TRANSPORT=pipe python3 tests/net_link_guest.py \
  --system build/link_system --fixtures build/link_fixtures \
  --output build/link_guest
```

The fixture's explicit qtest channel is absent from ordinary QEMU invocations.
Its PCI configuration writes occur only after service stop/wait and while vCPUs
are paused. The host assigns the same exclusive resources to the replacement;
it does not enable old queues or carry an old device grant across insertion.

## Retained failures and limits

An initial build rejected an oversized native service ELF. A default nonzero
link-state initializer had moved the large stack object from BSS to data. The
fix restores zero initialization and assigns the runtime value in initialize;
the ordinary 128 KiB loader bound remains unchanged. The build failure log is
retained.

The first real guest passed link recovery but stopped at unacknowledged PCI
eject. Its replacement attempt also supplied a boolean to QEMU's string-valued
`disable-legacy` property; that test error is retained and not presented as an
OS blocker. Separate diagnostics established actual QOM removal and the new
device's unassigned resources, then tested host preparation. They are labeled
diagnostic only. The final report above reran all steps with matching sources,
the observer-lifetime fix, a live old caller and exact resource checks.

This report does not qualify physical NIC hardware, multicore device teardown,
an unannounced hot-unplug during active DMA, automatic PCI resource assignment,
or recovery from a quarantined device. Those require their own mechanisms and
evidence; virtual results are not substituted for them.
