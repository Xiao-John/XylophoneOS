// SPDX-License-Identifier: Apache-2.0
#include "drivers/virtio_net.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <initializer_list>
using namespace xos;
using namespace xos::user::virtio_net;

namespace {
alignas(4096) u8 ring[queue_bytes];
struct used_element { u32 id, length; };
auto* available = reinterpret_cast<u16*>(ring + 1024);
auto* used = reinterpret_cast<u16*>(ring + 2048);
auto* entries = reinterpret_cast<used_element*>(ring + 2052);
u8 frame[frame_limit]{};
u8 received[frame_limit]{};

void reset_memory() { std::memset(ring, 0, sizeof(ring)); }
void initialize(split_queue& queue, bool receive) {
    reset_memory();
    queue.initialize(reinterpret_cast<u64>(ring), 0x200000, receive);
}
void receive_completion(u16 index, u32 id, u32 length = 72) {
    entries[index % queue_size] = {id, length};
    used[1] = static_cast<u16>(index + 1);
}

void capabilities() {
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
}

void tx_capacity() {
    split_queue tx; initialize(tx, false);
    frame[0] = 0xa5; frame[13] = 0x06;
    assert(tx.transmit(frame, 13) == device_invalid);
    assert(tx.transmit(nullptr, 60) == device_invalid);
    assert(tx.transmit(frame, frame_limit + 1) == device_invalid);
    for (u32 i = 0; i < queue_size; ++i) assert(tx.transmit(frame, 60) == 0);
    assert(tx.transmit(frame, 60) == device_busy);
    assert(available[1] == queue_size && ring[4096 + 12] == 0xa5);
    for (u32 i = 0; i < 12; ++i) assert(ring[4096 + i] == 0);
    entries[0] = {0, 0}; used[1] = 1;
    assert(tx.transmit(frame, 60) == 0);
    entries[1] = {queue_size, 0}; used[1] = 2;
    assert(tx.reclaim_transmit() == device_io);
}

void tx_wrap() {
    split_queue tx; initialize(tx, false);
    for (u32 i = 0; i < 65540; ++i) {
        assert(tx.transmit(frame, 60) == 0);
        entries[i % queue_size] = {0, 0}; used[1] = static_cast<u16>(i + 1);
        assert(tx.reclaim_transmit() == 0);
    }
    assert(available[1] == 4);
}

void rx_frame() {
    split_queue rx; initialize(rx, true);
    auto* packet = ring + 4096 + 5 * buffer_bytes;
    packet[12] = 0x52;
    receive_completion(0, 5);
    assert(rx.receive(received, sizeof(received)) == 60 && received[0] == 0x52 && available[1] == queue_size + 1);
    assert(rx.receive(received, sizeof(received)) == 0);
    receive_completion(1, 5, 12 + frame_limit);
    packet[12 + frame_limit - 1] = 0x39;
    assert(rx.receive(received, sizeof(received)) == frame_limit && received[frame_limit - 1] == 0x39);
    receive_completion(2, 5, 12 + 14);
    assert(rx.receive(received, sizeof(received)) == 14);
}

void rx_invalid_length() {
    for (u32 length : {0u, 25u, 1527u, 2048u, 0xffffffffu}) {
        split_queue rx; initialize(rx, true);
        receive_completion(0, 0, length);
        assert(rx.receive(received, sizeof(received)) == device_io);
        assert(available[1] == queue_size);
    }
}

void rx_header() {
    for (u32 offset : {0u, 1u}) {
        split_queue rx; initialize(rx, true);
        ring[4096 + offset] = 1;
        receive_completion(0, 0);
        assert(rx.receive(received, sizeof(received)) == device_io);
        assert(available[1] == queue_size);
    }
}

void used_distance() {
    split_queue rx; initialize(rx, true);
    used[1] = queue_size + 1;
    assert(rx.receive(received, sizeof(received)) == device_io);
    split_queue tx; initialize(tx, false);
    used[1] = queue_size + 1;
    assert(tx.reclaim_transmit() == device_io);
    initialize(rx, true);
    receive_completion(0, 5); receive_completion(1, 7);
    assert(rx.receive(received, sizeof(received)) == 60);
    used[1] = 1; // Device regresses below the already validated completion.
    assert(rx.receive(received, sizeof(received)) == device_io);
}

void reinitialize_dirty() {
    split_queue tx;
    std::memset(ring, 0xa5, sizeof(ring));
    tx.initialize(reinterpret_cast<u64>(ring), 0x200000, false);
    assert(available[0] == 0 && available[1] == 0 && used[0] == 0 && used[1] == 0);
    assert(tx.transmit(frame, 60) == 0);
    // Initialize again on the same backing pages after the device has reset.
    tx.initialize(reinterpret_cast<u64>(ring), 0x200000, true);
    assert(available[0] == 0 && available[1] == queue_size && used[0] == 0 && used[1] == 0);
    assert(tx.receive(received, sizeof(received)) == 0);
}

void rx_duplicate_batch() {
    split_queue rx; initialize(rx, true);
    receive_completion(0, 5); receive_completion(1, 5);
    assert(rx.receive(received, sizeof(received)) == device_io);
    assert(available[1] == queue_size); // No duplicate descriptor was republished.
}

void rx_pending_ownership() {
    split_queue rx; initialize(rx, true);
    receive_completion(0, 5); receive_completion(1, 7);
    assert(rx.receive(received, sizeof(received)) == 60);
    // Descriptor 7 is validated but still waiting for delivery to the caller.
    receive_completion(2, 7);
    assert(rx.receive(received, sizeof(received)) == device_io);
    assert(available[1] == queue_size + 1);

    initialize(rx, true);
    receive_completion(0, 5); receive_completion(1, 7);
    assert(rx.receive(received, sizeof(received)) == 60);
    receive_completion(2, 5); // Reposted 5 is valid even while 7 is pending.
    assert(rx.receive(received, sizeof(received)) == 60);
    assert(rx.receive(received, sizeof(received)) == 60);
    assert(rx.receive(received, sizeof(received)) == 0);
}

void rx_reuse_and_wrap() {
    split_queue rx; initialize(rx, true);
    for (u32 i = 0; i < 65540; i += 2) {
        receive_completion(static_cast<u16>(i), 5);
        receive_completion(static_cast<u16>(i + 1), 7);
        assert(rx.receive(received, sizeof(received)) == 60);
        assert(rx.receive(received, sizeof(received)) == 60);
        assert(rx.receive(received, sizeof(received)) == 0);
    }
    assert(available[1] == queue_size + 4);
}

void rx_snapshot() {
    split_queue rx; initialize(rx, true);
    receive_completion(0, 5); receive_completion(1, 7);
    assert(rx.receive(received, sizeof(received)) == 60);
    // Pending metadata must be the validated snapshot, not a second DMA read.
    entries[1] = {queue_size, 0xffffffffu};
    assert(rx.receive(received, sizeof(received)) == 60);
}

void failure_latched() {
    split_queue rx; initialize(rx, true);
    receive_completion(0, queue_size);
    assert(rx.receive(received, sizeof(received)) == device_io);
    entries[0] = {0, 72};
    assert(rx.receive(received, sizeof(received)) == device_io);
    assert(available[1] == queue_size);

    split_queue tx; initialize(tx, false);
    assert(tx.transmit(frame, 60) == 0);
    entries[0] = {0, 0}; entries[1] = {0, 0}; used[1] = 2;
    assert(tx.reclaim_transmit() == device_io);
    used[1] = 1;
    assert(tx.transmit(frame, 60) == device_io);
    assert(available[1] == 1);
}

void queue_direction() {
    split_queue queue;
    assert(queue.transmit(frame, 60) == device_closed);
    assert(queue.receive(received, sizeof(received)) == device_closed);
    assert(queue.reclaim_transmit() == device_closed);
    initialize(queue, true);
    assert(queue.transmit(frame, 60) == device_invalid);
    assert(queue.reclaim_transmit() == device_invalid);
    initialize(queue, false);
    assert(queue.receive(received, sizeof(received)) == device_invalid);
}
}

int main(int argc, char** argv) {
    const struct scenario { const char* name; void (*run)(); } scenarios[] = {
        {"capabilities", capabilities}, {"tx_capacity", tx_capacity}, {"tx_wrap", tx_wrap},
        {"rx_frame", rx_frame}, {"rx_invalid_length", rx_invalid_length}, {"rx_header", rx_header},
        {"used_distance", used_distance}, {"reinitialize_dirty", reinitialize_dirty},
        {"rx_duplicate_batch", rx_duplicate_batch}, {"rx_pending_ownership", rx_pending_ownership},
        {"rx_reuse_and_wrap", rx_reuse_and_wrap}, {"rx_snapshot", rx_snapshot},
        {"failure_latched", failure_latched}, {"queue_direction", queue_direction},
    };
    u32 passed = 0;
    for (const auto& item : scenarios) {
        if (argc == 1 || (argc == 2 && std::strcmp(argv[1], item.name) == 0)) { item.run(); ++passed; }
    }
    assert(passed != 0);
    std::printf("VIRTIO_NET_IMPLEMENTATION_SCENARIOS_PASSED=%u\n", passed);
}
