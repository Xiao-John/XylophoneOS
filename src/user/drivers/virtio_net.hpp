// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/device.hpp>

namespace xos::user::virtio_net {
inline constexpr u16 queue_size = 64;
inline constexpr u32 frame_limit = 1514, buffer_bytes = 2048, queue_bytes = 4096 + queue_size * buffer_bytes;
struct capability { u32 bar, offset, length, multiplier; };
bool inspect_capabilities(const u32 (&configuration)[64], const u64 (&bar_lengths)[6], capability (&out)[4]);

class split_queue {
public:
    void initialize(u64 address, u64 physical, bool receive);
    i64 transmit(const u8* frame, u32 length);
    i64 receive(u8* frame, u32 capacity);
    i64 reclaim_transmit();
    u64 physical() const { return physical_; }
private:
    u64 address_ = 0, physical_ = 0;
    u16 available_ = 0, consumed_ = 0;
    bool active_[queue_size]{};
    void publish(u16 descriptor);
};

class driver {
public:
    i64 initialize(u64 grant);
    i64 transmit(const u8* frame, u32 length);
    i64 receive(u8* frame, u32 capacity);
    i64 wait(u64 deadline);
    i64 shutdown();
    const u8* mac() const { return mac_; }
    u64 irq_count() const { return irq_count_; }
private:
    u64 grant_ = 0, event_ = 0, acknowledged_ = 0, irq_count_ = 0;
    bool ready_ = false;
    volatile u8 *common_ = nullptr, *isr_ = nullptr;
    volatile u16* notify_[2]{};
    u8 mac_[6]{};
    split_queue queues_[2];
    i64 configure();
    bool reset();
    template<class value> value read(u32 offset) const { return *reinterpret_cast<volatile value*>(common_ + offset); }
    template<class value> void write(u32 offset, value data) {
        *reinterpret_cast<volatile value*>(common_ + offset) = data;
        __atomic_thread_fence(__ATOMIC_SEQ_CST);
    }
};
}
