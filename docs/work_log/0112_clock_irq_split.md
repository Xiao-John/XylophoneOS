# 0112 Generic clock/IRQ repair split from PR #20

2026-10-30. New branch from freshly fetched upstream `main` at
`860405018c3f200b39efbe442147e89a3d2a399e`; original PR #20 head was rechecked
at `da1a47c0b8455be82ba90aaf5bea393066839ac4` and was not modified.

## Scope

This branch extracts the accepted generic timekeeping/IRQ direction: one shared
PIT-backed monotonic counter, pure PIC EOI, one pre-console PIC/PIT initialization,
and IRQ0 time advancement before `tasks_enter()` without scheduler/waiter activity.
`sys_ticks`, monotonic waits and the RTC anchor use the same clock. The platform
code owns only generic PIT/PIC setup and acknowledgment. The test-only
`--clock-irq-probe` build profile is isolated from the default image.

The diff contains no `virtio_net.cpp`, VirtIO queue, frame TX/RX, NIC lifecycle,
network diagnostic command, NIC build switch, device-specific device API, syscall,
or public system ABI change. The old kernel driver and its prior experiment/failure
evidence remain on the original PR #20 branch. `claim_diagnostic_irq`, diagnostic
ELCR ownership, and the generic `device_irq` test route from the broader PR stack
were deliberately excluded; the clock probe tests EOI directly and real PIC/PIT
behavior in QEMU.

## Verification

Default build `0394a5906b68ae38` was built from this source tree. Its manifest lists
no kernel NIC source, the build command has no network-driver option, and
`kernel.elf` has no VirtIO-Net symbols. It boots and passes:

- E02 kernel/boot verification: 18 checks.
- G02 actual display, PS/2 input and service lifecycle: 19 groups.
- Thread scheduling/wait lifecycle: 15 groups.
- Dash C1 thread-pipe/wait readiness and close-race test: 2 guest runs.
- Real Dash C3 guest shell: 12 checks with the current profile.

The separate clock/IRQ audit build `d431c432493b546d` links only the test-only
`clock_irq_probe.cpp`. In actual QEMU, the `irq-audit` command verified IF-clear
entry, pure EOI without time changes, idempotent initialization, three real PIT
ticks before scheduler entry, no pre-run scheduling/allocation, and the canonical
monotonic conversion. A compiled user program then exercised monotonic and
realtime clock reads, `sleep_until`, timeout waits, and resource return twice from
xsh and once through a real Dash script. QEMU is 11.1.2 TCG, `pc-i440fx-10.0`,
`qemu64,+rdrand`, one CPU, 512 MiB, no NIC.

Clock guest resources stayed at `[130278, 2, 0]`; the existing default guest
regressions returned to `[130279, 2, 0]`. Exact manifests, target and user ELF
hashes, QEMU command lines, guest logs and resource counts are in
`docs/reports/net_clock_irq_split_20261030/`.

The upstream review of PR #20 still requests a ring-3 VirtIO-Net driver and
independently reviewed generic device authorization, MMIO, DMA, IRQ delivery,
revocation and recovery mechanisms. None of those are implemented here. PR #20
remains `CHANGES_REQUESTED`; this clock/IRQ branch is independently reviewable
and does not satisfy or supersede the network architecture blocker.
