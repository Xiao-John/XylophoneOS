# DHCP recovery after a link transition (P1-I2)

The existing user-space VirtIO-net service now observes the negotiated VirtIO
network link status. A link transition retires the old DHCP application epoch
and starts a new bounded acquisition after link-up. It does not recover an old
TCP connection or turn a stale device grant into authority over another device.

## Driver signal and compatibility

When the modern VirtIO network device offers `VIRTIO_NET_F_STATUS` (bit 16),
the driver negotiates it and reads the little-endian device status field at
offset 6 of the device configuration. The link is up only when bit 0 is set.
It retries a bounded number of reads around the common configuration generation
to avoid accepting an inconsistent configuration sample. An unstable sample is
unavailable and causes the service to fail closed. The generic device grant
must still belong to the process before any status read.

A device without the status feature retains VirtIO's compatibility behavior:
the link is treated as up. Such a device cannot qualify automatic link-loss
detection through this interface. This interpretation follows the official
[VirtIO 1.2 network-device specification](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html).
There is no new public syscall, MMIO grant right or Net2 wire operation.

## Loss and re-acquisition

The service checks link state before normal input and timer processing. On loss,
it closes the application traffic gate, invalidates the published lease with
the existing `link_lost` reason, retires all application sessions and their
connection/ticket generations, clears DNS state and both configured resolvers,
stops DHCP, and removes the interface's old ARP and transport state. Queued RX
frames are drained without application delivery while the link is down.
Transmit checks the driver link status as well as the stack gate.

Time spent with the link down does not consume a new acquisition budget or
continue DHCP retry traffic. A subsequent up transition drains retained input
before starting a fresh DHCP transaction and acquisition clock. The new lease
still passes the sealed server/address/router/resolver policy and address
conflict detection before its tuple is published. It receives a new application
epoch even if the same address happens to be offered. An initial down link
follows this same path and has no static-address fallback.

Old UDP payloads queued behind unresolved ARP, pending TCP SYNs, existing
connection handles, resolver subscriptions and cached answers cannot become
valid again after re-acquisition. An unsolicited late ARP answer may update
new-epoch neighbor state under the ordinary stack rules; it cannot restore
the retired old packet queue. Applications must authenticate a current session
and open new connections. DNS success still grants no egress authority.

The static-address profile fails closed on an observed link loss. Automatic
static recovery is not claimed because that path has no qualified fresh ACD
and lease authority transition.

## Device disappearance is a separate boundary

The current sys89 configuration query returns the snapshot sealed when a
device grant was created. It is not a live PCI presence or device-generation
query. A live process must not infer hotplug identity from an old BAR mapping,
an all-ones MMIO value, or a cached PCI tuple. This module does not introduce a
PCI hotplug manager, firmware resource allocator or generic presence event ABI.

A controlled replacement must first stop and wait for the old service so that
the driver resets queues and releases DMA/MMIO authority. After an actual PCI
device removal and insertion, the controller must obtain a new grant from the
current device identity and launch a new service; that service must perform new
DHCP and ACD. A QMP `set_link` operation alone proves neither device removal nor
device reappearance. The generic PCI reset observer is retired on grant disable,
after DMA-stop observation. Its mapping is unmapped and its bounded slot becomes
available for a fresh inspection. A new grant at the same BDF must map the new
function's current BAR, never reuse the former observer. Failed unmap leaves
that slot occupied and prevents admission; a rejected mapping never publishes
an observer. This changes no public device grant right or wire format.

The controlled QEMU fixture preserves the guest's unacknowledged ACPI eject
request as a separate observation. It may then force `realized=false` through
QOM and must observe actual removal through `query-pci` before `device_add`.
An unconfigured replacement must fail closed. To test the service recovery
boundary independently of the absent guest PCI allocator, the host fixture
may pause vCPUs and use QEMU's documented [qtest PIO protocol](https://www.qemu.org/docs/master/devel/testing/qtest.html)
to assign the old, now-unused exclusive BAR ranges and IRQ to the **new**
function. Decode and bus mastering stay disabled until the new grant lifecycle
enables them. These are PCI configuration accesses, not reads of old MMIO.
The report distinguishes this host preparation from OS firmware/resource
configuration or ACPI eject support.

Unexpected device disappearance and automatic rebinding remain unsupported
without the missing generic identity/presence and PCI resource mechanisms.
Physical NIC qualification requires separate hardware evidence and is not
inferred from VirtIO or host tests.

## Qualification and rollback

The production DHCP/lwIP host suite exercises an initially down link, prolonged
down time, invalidation, a new address, fresh ACD, and retirement of queued UDP
and TCP work. Existing VirtIO queue tests and ordinary stack/service scenarios
remain separate regressions.

`tests/net_link_guest.py` binds a freshly built system, its native SDK and caller,
the sealed `link_profile.json`, serial output and Ethernet capture. Its QMP link
transition is observed by the actual driver; independent DHCP/ARP peers verify
new transactions, ACD probes and application nonces. The probe holds old UDP and
TCP behind real unresolved ARP before loss, then injects the late ARP answer
after a new lease. The runner separately tests unconfigured replacement denial
and controlled `device_del`/QOM removal/`device_add`, with explicit host PCI
preparation after service stop. An old caller remains alive until the new
service appears and must reject its identity. A new DHCP transaction, fresh ACD,
a fresh application nonce and exact resource recovery are required. Defined
tests are not pass evidence; the corresponding report records the actual
outcome and hardware boundary.

Rollback selects the previous matching image and SDK. The installation policy
schema, ordinary Net2 clients and prior single-resolver profiles are unchanged.
