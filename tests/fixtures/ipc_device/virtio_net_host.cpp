// SPDX-License-Identifier: Apache-2.0
#include "drivers/virtio_net.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
using namespace xos;
using namespace xos::user::virtio_net;
alignas(4096) u8 ring[queue_bytes];
struct used_element { u32 id, length; };

int main() {
    u32 configuration[64]{}; u64 bars[6]{0x4000}; capability caps[4]{};
    configuration[0] = 0x10411af4; configuration[1] = 1u << 20; configuration[0x34 / 4] = 0x40;
    const u32 offsets[]{0x40, 0x50, 0x64, 0x74};
    for (u32 i = 0; i < 4; ++i) {
        const u32 next = i == 3 ? 0 : offsets[i + 1], length = i == 1 ? 20 : 16;
        const u32 slot = offsets[i] / 4;
        configuration[slot] = 9 | (next << 8) | (length << 16) | ((i + 1) << 24);
        configuration[slot + 2] = i * 0x1000; configuration[slot + 3] = 0x1000;
        if (i == 1) configuration[slot + 4] = 4;
    }
    assert(inspect_capabilities(configuration, bars, caps) && caps[1].multiplier == 4);
    configuration[0x74 / 4] |= 0x4000;
    assert(!inspect_capabilities(configuration, bars, caps));
    configuration[0x74 / 4] &= ~0xff00u;
    configuration[0x64 / 4 + 2] = 0x4000;
    assert(!inspect_capabilities(configuration, bars, caps));
    configuration[0x64 / 4 + 2] = 0x2000;
    configuration[0x50 / 4] -= 4u << 16;
    assert(!inspect_capabilities(configuration, bars, caps));

    split_queue tx;
    tx.initialize(reinterpret_cast<u64>(ring), 0x200000, false);
    u8 frame[frame_limit]{}; frame[0] = 0xa5; frame[13] = 0x06;
    assert(tx.transmit(frame, 13) == device_invalid);
    for (u32 i = 0; i < queue_size; ++i) assert(tx.transmit(frame, 60) == 0);
    assert(tx.transmit(frame, 60) == device_busy);
    auto* available = reinterpret_cast<u16*>(ring + 1024);
    auto* used = reinterpret_cast<u16*>(ring + 2048);
    auto* entries = reinterpret_cast<used_element*>(ring + 2052);
    assert(available[1] == queue_size && ring[4096 + 12] == 0xa5);
    for (u32 i = 0; i < 12; ++i) assert(ring[4096 + i] == 0);
    entries[0] = {0, 0}; used[1] = 1;
    assert(tx.transmit(frame, 60) == 0);
    entries[1] = {queue_size, 0}; used[1] = 2;
    assert(tx.reclaim_transmit() == device_io);

    std::memset(ring, 0, sizeof(ring));
    split_queue wrapped; wrapped.initialize(reinterpret_cast<u64>(ring), 0x200000, false);
    for (u32 i = 0; i < 65540; ++i) {
        assert(wrapped.transmit(frame, 60) == 0);
        entries[i % queue_size] = {0, 0}; used[1] = static_cast<u16>(i + 1);
        assert(wrapped.reclaim_transmit() == 0);
    }
    assert(available[1] == 4);

    std::memset(ring, 0, sizeof(ring));
    split_queue rx; rx.initialize(reinterpret_cast<u64>(ring), 0x300000, true);
    auto* packet = ring + 4096 + 5 * buffer_bytes;
    packet[10] = 1; packet[12] = 0x52;
    entries[0] = {5, 72}; used[1] = 1;
    u8 received[frame_limit]{};
    assert(rx.receive(received, sizeof(received)) == 60 && received[0] == 0x52 && available[1] == queue_size + 1);
    assert(rx.receive(received, sizeof(received)) == 0);
    entries[1] = {5, 2048}; used[1] = 2;
    assert(rx.receive(received, sizeof(received)) == device_io);
    entries[1].length = 72; packet[0] = 1;
    assert(rx.receive(received, sizeof(received)) == device_io);
    packet[0] = 0; used[1] = static_cast<u16>(queue_size + 2);
    assert(rx.receive(received, sizeof(received)) == device_io);
    puts("VIRTIO_NET_IMPLEMENTATION_SCENARIOS_PASSED=5");
}
