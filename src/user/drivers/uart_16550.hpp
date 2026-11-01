// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>

namespace xos::user::uart {
// Single-owner COM1 driver. Calls must be serialized by its owning service.
// Device permission and COM1 handoff must be granted before start().
struct statistics { u64 software_drops, hardware_overruns, framing_errors, parity_errors, breaks; };

class driver {
    static constexpr u32 capacity = 1024;
    u8 data_[capacity]{};
    u32 head_ = 0, length_ = 0;
    u64 irq_token_ = 0;
    statistics stats_{};
    bool started_ = false;
    u8 status();
public:
    driver() = default;
    driver(const driver&) = delete;
    driver& operator=(const driver&) = delete;
    i64 start();
    i64 wait(u64 deadline);
    i64 service_irq(u64 sequence);
    i64 read(u8* output, u32 limit);
    i64 readable() const;
    i64 write(const u8* input, u32 length);
    i64 arm_write();
    i64 transmitter_empty();
    i64 flush_input();
    i64 close();
    u64 token() const { return irq_token_; }
    statistics counters() const { return stats_; }
};
}
