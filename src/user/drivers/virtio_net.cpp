// SPDX-License-Identifier: Apache-2.0
// Modern PCI transport and split rings, VirtIO 1.2 §§2.6, 4.1, 5.1.
// Device protocol, reset writes and frames stay entirely in user mode.
#include "virtio_net.hpp"
#include <xos/thread_abi.hpp>

namespace xos::user::virtio_net {
namespace {
struct descriptor { u64 address; u32 length; u16 flags, next; };
struct used_element { u32 id, length; };
static_assert(sizeof(descriptor) == 16 && sizeof(used_element) == 8);
constexpr u32 header_bytes = 12, available_offset = 1024, used_offset = 2048;
void fence() { __atomic_thread_fence(__ATOMIC_SEQ_CST); }
u64 monotonic() { return static_cast<u64>(sdk::syscall(sys_clock_monotonic)); }
}

bool inspect_capabilities(const u32 (&configuration)[64], const u64 (&bar_lengths)[6], capability (&out)[4]) {
    const u32 identity = configuration[0];
    if ((identity & 0xffff) != 0x1af4 || ((identity >> 16) != 0x1041 && (identity >> 16) != 0x1000) ||
        !(configuration[1] & (1u << 20))) return false;
    bool seen[64]{}; bool found[4]{};
    u32 offset = configuration[0x34 / 4] & 0xff;
    while (offset) {
        if (offset < 0x40 || offset > 0xfc || (offset & 3) || seen[offset / 4]) return false;
        seen[offset / 4] = true;
        const u32 header = configuration[offset / 4];
        const u32 length = (header >> 16) & 0xff, kind = header >> 24;
        if ((header & 0xff) == 9) {
            if (length < 16 || length > 256 - offset) return false;
            if (kind >= 1 && kind <= 4) {
                if (found[kind - 1] || (kind == 2 && length < 20)) return false;
                const u32 bar = configuration[offset / 4 + 1] & 0xff;
                const u32 start = configuration[offset / 4 + 2], bytes = configuration[offset / 4 + 3];
                const u32 minimum = kind == 1 ? 56 : kind == 2 ? 2 : kind == 3 ? 1 : 6;
                if (bar >= 6 || bytes < minimum || bytes > device_mapping_slot_bytes - 4096 ||
                    start > bar_lengths[bar] || bytes > bar_lengths[bar] - start ||
                    (start & (kind == 1 ? 3u : kind == 2 ? 1u : 0u))) return false;
                out[kind - 1] = {bar, start, bytes, kind == 2 ? configuration[offset / 4 + 4] : 0};
                found[kind - 1] = true;
            }
        }
        offset = (header >> 8) & 0xff;
    }
    return found[0] && found[1] && found[2] && found[3];
}

void split_queue::initialize(u64 address, u64 physical, bool receive) {
    address_ = address; physical_ = physical; available_ = consumed_ = 0;
    auto* descriptors = reinterpret_cast<volatile descriptor*>(address_);
    for (u16 i = 0; i < queue_size; ++i) {
        descriptors[i].address = physical_ + 4096 + u64{i} * buffer_bytes;
        descriptors[i].length = receive ? buffer_bytes : 0;
        descriptors[i].flags = receive ? 2 : 0; descriptors[i].next = 0;
        active_[i] = receive;
        if (receive) publish(i);
    }
}
void split_queue::publish(u16 index) {
    auto* available = reinterpret_cast<volatile u16*>(address_ + available_offset);
    available[2 + available_ % queue_size] = index;
    fence(); ++available_; available[1] = available_; fence();
}
i64 split_queue::reclaim_transmit() {
    const auto* used = reinterpret_cast<volatile u16*>(address_ + used_offset);
    const u16 completed = used[1]; fence();
    if (static_cast<u16>(completed - consumed_) > queue_size) return device_io;
    const auto* elements = reinterpret_cast<volatile used_element*>(address_ + used_offset + 4);
    while (consumed_ != completed) {
        const u32 id = elements[consumed_ % queue_size].id;
        if (id >= queue_size || !active_[id]) return device_io;
        active_[id] = false; ++consumed_;
    }
    return 0;
}
i64 split_queue::transmit(const u8* frame, u32 length) {
    if (!frame || length < 14 || length > frame_limit) return device_invalid;
    const i64 reclaimed = reclaim_transmit();
    if (reclaimed) return reclaimed;
    u16 id = 0;
    while (id < queue_size && active_[id]) ++id;
    if (id == queue_size) return device_busy;
    auto* buffer = reinterpret_cast<u8*>(address_ + 4096 + u64{id} * buffer_bytes);
    for (u32 i = 0; i < header_bytes; ++i) buffer[i] = 0;
    for (u32 i = 0; i < length; ++i) buffer[header_bytes + i] = frame[i];
    reinterpret_cast<volatile descriptor*>(address_)[id].length = header_bytes + length;
    active_[id] = true; publish(id); return 0;
}
i64 split_queue::receive(u8* frame, u32 capacity) {
    if (!frame || capacity < frame_limit) return device_invalid;
    const auto* used = reinterpret_cast<volatile u16*>(address_ + used_offset);
    const u16 completed = used[1]; fence();
    if (completed == consumed_) return 0;
    if (static_cast<u16>(completed - consumed_) > queue_size) return device_io;
    const auto* elements = reinterpret_cast<volatile used_element*>(address_ + used_offset + 4);
    const u32 id = elements[consumed_ % queue_size].id, length = elements[consumed_ % queue_size].length;
    if (id >= queue_size || !active_[id] || length < header_bytes + 14 || length > header_bytes + frame_limit) return device_io;
    const auto* buffer = reinterpret_cast<const volatile u8*>(address_ + 4096 + u64{id} * buffer_bytes);
    // num_buffers is meaningful only when VIRTIO_NET_F_MRG_RXBUF is negotiated.
    if (buffer[0] || buffer[1]) return device_io;
    for (u32 i = header_bytes; i < length; ++i) frame[i - header_bytes] = buffer[i];
    ++consumed_; publish(static_cast<u16>(id)); return length - header_bytes;
}

bool driver::reset() {
    write<u8>(20, 0);
    const u64 start = monotonic();
    const u64 deadline = start > ~u64{0} - 1000000000ull ? ~u64{0} : start + 1000000000ull;
    while (read<u8>(20) != 0) {
        const u64 now = monotonic();
        if (now >= deadline) return false;
        const u64 next = deadline - now < thread_tick_ns ? deadline : now + thread_tick_ns;
        if (sdk::syscall(sys_sleep_until, next) != 0) return false;
    }
    fence(); return true;
}
i64 driver::initialize(u64 grant) {
    if (grant_ || !grant) return device_invalid;
    grant_ = grant;
    const i64 result = configure();
    if (result) { (void)shutdown(); return result; }
    ready_ = true; return 0;
}
i64 driver::configure() {
    u32 configuration[64]{}; u64 lengths[6]{}; capability capabilities[4]{};
    for (u32 offset = 0; offset < 256; offset += 4) {
        const i64 result = device::configuration(grant_, offset, configuration[offset / 4]);
        if (result) return result;
    }
    for (u32 index = 0; index < 6; ++index) {
        device_output resource{};
        const i64 result = device::query(grant_, index, resource);
        if (result && result != device_no_device) return result;
        if (!result) lengths[index] = resource.length;
    }
    if (!inspect_capabilities(configuration, lengths, capabilities)) return device_no_device;
    volatile u8* registers[4]{};
    for (u32 i = 0; i < 4; ++i) {
        const auto& cap = capabilities[i];
        const u64 begin = cap.offset & ~u64{4095};
        const u64 size = (u64{cap.offset} + cap.length + 4095 - begin) & ~u64{4095};
        device_output mapping{};
        const i64 result = device::map(grant_, cap.bar, begin, size, i == 2 || i == 3 ? 1 : 3, mapping);
        if (result) return result;
        registers[i] = reinterpret_cast<volatile u8*>(mapping.address + cap.offset - begin);
        if (i == 0) common_ = registers[0];
    }
    isr_ = registers[2];
    if (!reset()) return device_timeout;
    write<u8>(20, 1); write<u8>(20, 3);
    write<u32>(0, 1); const u32 high = read<u32>(4);
    write<u32>(0, 0); const u32 low = read<u32>(4);
    if (!(high & 1) || !(low & (1u << 5))) return device_no_device;
    write<u32>(8, 1); write<u32>(12, 1);
    write<u32>(8, 0); write<u32>(12, 1u << 5);
    write<u8>(20, 11);
    if (!(read<u8>(20) & 8) || read<u16>(18) < 2) return device_io;
    bool stable = false;
    for (u32 attempt = 0; attempt < 8 && !stable; ++attempt) {
        const u8 generation = read<u8>(21);
        for (u32 i = 0; i < 6; ++i) mac_[i] = registers[3][i];
        fence(); stable = generation == read<u8>(21);
    }
    if (!stable) return device_io;
    device_output dma{};
    const i64 allocation = device::dma_allocate(grant_, 2 * queue_bytes, 4096, device_dma_direction::bidirectional, dma);
    if (allocation) return allocation;
    write<u16>(16, 0xffff);
    for (u16 index = 0; index < 2; ++index) {
        write<u16>(22, index);
        if (read<u16>(24) < queue_size || read<u16>(28)) return device_no_device;
        write<u16>(24, queue_size); write<u16>(26, 0xffff);
        if (read<u16>(24) != queue_size) return device_io;
        const u64 offset = u64{read<u16>(30)} * capabilities[1].multiplier;
        if ((offset & 1) || offset > capabilities[1].length || capabilities[1].length - offset < 2) return device_io;
        notify_[index] = reinterpret_cast<volatile u16*>(registers[1] + offset);
        queues_[index].initialize(dma.address + u64{index} * queue_bytes, dma.offset + u64{index} * queue_bytes, index == 0);
        const u64 physical = queues_[index].physical();
        for (u32 reg = 32; reg <= 48; reg += 8) {
            const u64 address = physical + (reg == 40 ? available_offset : reg == 48 ? used_offset : 0);
            write<u32>(reg, static_cast<u32>(address));
            write<u32>(reg + 4, static_cast<u32>(address >> 32));
        }
        write<u16>(28, 1);
        if (read<u16>(28) != 1) return device_io;
    }
    device_output event{};
    const i64 bound = device::irq_bind(grant_, event);
    if (bound) return bound;
    event_ = event.token; acknowledged_ = event.offset;
    write<u8>(20, 15);
    if (read<u8>(20) != 15) return device_io;
    *notify_[0] = 0; fence(); return 0;
}
i64 driver::transmit(const u8* frame, u32 length) {
    if (!ready_) return device_closed;
    const i64 result = queues_[1].transmit(frame, length);
    if (!result) { *notify_[1] = 1; fence(); }
    return result;
}
i64 driver::receive(u8* frame, u32 capacity) {
    if (!ready_) return device_closed;
    const i64 result = queues_[0].receive(frame, capacity);
    if (result > 0) { *notify_[0] = 0; fence(); }
    return result;
}
i64 driver::wait(u64 deadline) {
    if (!ready_) return device_closed;
    device_output event{};
    const i64 result = device::irq_wait(event_, acknowledged_, deadline, event);
    if (result) return result;
    const u8 cause = *isr_; (void)cause; fence();
    const i64 ack = device::irq_ack(event_, event.offset);
    if (ack) return ack;
    acknowledged_ = event.offset; ++irq_count_;
    return queues_[1].reclaim_transmit();
}
i64 driver::shutdown() {
    ready_ = false;
    if (!grant_) return 0;
    device_output resource{};
    const i64 alive = device::query(grant_, device_configuration_index, resource);
    bool stopped = true;
    if (!alive && common_) stopped = reset();
    const i64 result = device::close(grant_);
    grant_ = event_ = 0; common_ = isr_ = nullptr;
    return result ? result : stopped ? 0 : device_timeout;
}
}
