// SPDX-License-Identifier: Apache-2.0
#include "uart_16550.hpp"
#include <xos/thread_abi.hpp>

namespace xos::user::uart {
namespace {
constexpr u16 base = 0x3f8;
constexpr u8 ready = 0x01, overrun = 0x02, parity = 0x04, framing = 0x08, broken = 0x10, tx_ready = 0x20;
u8 read_port(u16 port) {
    u8 result;
    __asm__ volatile("inb %1, %0" : "=a"(result) : "Nd"(port));
    return result;
}
void write_port(u16 port, u8 value) {
    __asm__ volatile("outb %0, %1" : : "a"(value), "Nd"(port));
}
void count(u64& value) { if (value != ~u64{0}) ++value; }
}

u8 driver::status() {
    const u8 value = read_port(base + 5);
    if (value & overrun) count(stats_.hardware_overruns);
    if (value & parity) count(stats_.parity_errors);
    if (value & framing) count(stats_.framing_errors);
    if (value & broken) count(stats_.breaks);
    return value;
}

i64 driver::start() {
    if (started_) return process_error_state;
    // The kernel keeps IRQ4 masked while the new owner initializes. A prior
    // owner could have left DLAB or interrupt enables set: normalize the line
    // before binding the IRQ, without intentionally clearing the input FIFO.
    write_port(base + 3, 0x03);
    write_port(base + 1, 0x00);
    write_port(base + 3, 0x83);
    write_port(base, 0x01);
    write_port(base + 1, 0x00);
    write_port(base + 3, 0x03);
    write_port(base + 4, 0x0b);
    const i64 result = sdk::irq_event(irq_event_action::bind, pio_resource_com1);
    if (result <= 0) return result < 0 ? result : process_error_state;
    irq_token_ = static_cast<u64>(result);
    // Leave the FIFO intact. Enable RX and line status after binding.
    write_port(base + 1, 0x05);
    started_ = true;
    return 0;
}

i64 driver::wait(u64 deadline) {
    if (!started_) return process_error_state;
    return sdk::irq_event(irq_event_action::wait, irq_token_, deadline);
}

i64 driver::service_irq(u64 sequence) {
    if (!started_ || sequence == 0) return process_error_state;
    // THRE is level-triggered on common 16550s. Disarm it until a blocked
    // writer explicitly rearms, including when another UART cause woke us.
    write_port(base + 1, 0x05);
    // The device remains IRQ-masked until ack. Bound work even if input keeps
    // arriving; a still-asserted source raises a new event after unmasking.
    for (u32 i = 0; i < 256; ++i) {
        const u8 line_status = status();
        if (line_status == 0xff) return process_error_state;
        if (!(line_status & ready)) break;
        const u8 byte = read_port(base);
        if (length_ == capacity) count(stats_.software_drops);
        else { data_[(head_ + length_) % capacity] = byte; ++length_; }
    }
    return sdk::irq_event(irq_event_action::ack, irq_token_, sequence);
}

i64 driver::readable() const { return started_ ? (length_ != 0 ? 1 : 0) : process_error_state; }

i64 driver::read(u8* output, u32 limit) {
    if (!started_) return process_error_state;
    if (output == nullptr && limit != 0) return process_error_invalid;
    u32 amount = 0;
    while (amount < limit && length_ != 0) {
        output[amount++] = data_[head_];
        head_ = (head_ + 1) % capacity;
        --length_;
    }
    return static_cast<i64>(amount);
}

i64 driver::write(const u8* input, u32 length) {
    if (!started_ || (input == nullptr && length != 0)) return process_error_invalid;
    u32 written = 0;
    while (written < length) {
        const u8 line_status = status();
        if (line_status == 0xff) return written != 0 ? static_cast<i64>(written) : process_error_state;
        if (!(line_status & tx_ready)) break;
        write_port(base, input[written++]);
    }
    return static_cast<i64>(written);
}

i64 driver::arm_write() {
    if (!started_) return process_error_state;
    write_port(base + 1, 0x07);
    return 0;
}

i64 driver::transmitter_empty() {
    if (!started_) return process_error_state;
    // TEMT includes the shift register; THRE alone is not a drain.
    const u8 line_status = status();
    if (line_status == 0xff) return process_error_state;
    return (line_status & 0x40) != 0 ? 1 : 0;
}

i64 driver::flush_input() {
    if (!started_) return process_error_state;
    // Bounded drain avoids monopolizing the CPU if input never stops. On
    // failure hardware bytes may already have been discarded; never claim an
    // atomic rollback. The caller serializes this with IRQ queue processing.
    for (u32 i = 0; i <= 256; ++i) {
        const u8 line_status = status();
        if (line_status == 0xff) return process_error_state;
        if ((line_status & ready) == 0) {
            head_ = 0; length_ = 0;
            return 0;
        }
        if (i == 256) return thread_error_busy;
        (void)read_port(base);
    }
    return process_error_state;
}

i64 driver::close() {
    if (!started_) return process_error_state;
    write_port(base + 1, 0);
    const i64 result = sdk::irq_event(irq_event_action::close, irq_token_);
    started_ = false;
    irq_token_ = 0;
    return result;
}
}
