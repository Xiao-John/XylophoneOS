#include <xos/block.hpp>
#include "arch/x86_64/io.hpp"

namespace xos::block {
namespace {
using arch::in_byte;
using arch::in_word;
using arch::out_byte;
using arch::out_word;
constexpr u16 data_port = 0x1f0;
constexpr u16 error_port = 0x1f1;
constexpr u16 count_port = 0x1f2;
constexpr u16 lba0_port = 0x1f3;
constexpr u16 lba1_port = 0x1f4;
constexpr u16 lba2_port = 0x1f5;
constexpr u16 drive_port = 0x1f6;
constexpr u16 status_port = 0x1f7;
constexpr u16 command_port = 0x1f7;
constexpr u8 status_err = 0x01;
constexpr u8 status_drq = 0x08;
constexpr u8 status_bsy = 0x80;

bool device_present;
u64 capacity_sectors;

void delay_400ns() {
    for (u32 i = 0; i < 4; ++i) { (void)in_byte(status_port); }
}

bool wait_not_busy() {
    for (u32 i = 0; i < 1000000; ++i) {
        const u8 status = in_byte(status_port);
        if ((status & status_bsy) == 0) { return (status & status_err) == 0; }
    }
    return false;
}

bool wait_drq() {
    for (u32 i = 0; i < 1000000; ++i) {
        const u8 status = in_byte(status_port);
        if ((status & status_err) != 0) { return false; }
        if ((status & status_bsy) == 0 && (status & status_drq) != 0) { return true; }
    }
    return false;
}

bool select_lba(u32 lba) {
    out_byte(drive_port, static_cast<u8>(0xe0 | ((lba >> 24) & 0x0f)));
    delay_400ns();
    if (!wait_not_busy()) { return false; }
    out_byte(count_port, 0);
    out_byte(lba0_port, 0);
    out_byte(lba1_port, 0);
    out_byte(lba2_port, 0);
    return true;
}

bool identify() {
    out_byte(drive_port, 0xa0);
    delay_400ns();
    out_byte(count_port, 0);
    out_byte(lba0_port, 0);
    out_byte(lba1_port, 0);
    out_byte(lba2_port, 0);
    out_byte(command_port, 0xec);
    if (!wait_drq()) { return false; }
    u16 words[256];
    for (u32 i = 0; i < 256; ++i) { words[i] = in_word(data_port); }
    const u32 low = words[60];
    const u32 high = words[61];
    const u64 sectors = (static_cast<u64>(high) << 16) | low;
    capacity_sectors = sectors;
    return sectors != 0 && sectors <= 0x0fffffff;
}

bool start_transfer(u64 sector, u32 count, u8 command) {
    if (!device_present || count == 0 || count > max_transfer_sectors ||
        sector >= capacity_sectors || sector + count > capacity_sectors ||
        sector > 0x0fffffff) { return false; }
    const auto lba = static_cast<u32>(sector);
    if (!select_lba(lba)) { return false; }
    out_byte(count_port, static_cast<u8>(count));
    out_byte(lba0_port, static_cast<u8>(lba & 0xff));
    out_byte(lba1_port, static_cast<u8>((lba >> 8) & 0xff));
    out_byte(lba2_port, static_cast<u8>((lba >> 16) & 0xff));
    out_byte(command_port, command);
    return true;
}
}

bool init() {
    device_present = false;
    capacity_sectors = 0;
    if (!identify()) { return false; }
    device_present = true;
    return true;
}

bool present() { return device_present; }
u64 sector_count() { return capacity_sectors; }

result read(u64 sector, void* buffer, u32 count) {
    if (!device_present) { return result::no_device; }
    if (buffer == nullptr || count == 0 || count > max_transfer_sectors) { return result::invalid; }
    if (!start_transfer(sector, count, 0x20)) { return result::invalid; }
    auto* target = static_cast<u16*>(buffer);
    for (u32 index = 0; index < count * 256; ++index) {
        if (index % 256 == 0 && !wait_drq()) { return result::timeout; }
        target[index] = in_word(data_port);
    }
    return wait_not_busy() ? result::none : result::io;
}

result write(u64 sector, const void* buffer, u32 count) {
    if (!device_present) { return result::no_device; }
    if (buffer == nullptr || count == 0 || count > max_transfer_sectors) { return result::invalid; }
    if (!start_transfer(sector, count, 0x30)) { return result::invalid; }
    const auto* source = static_cast<const u16*>(buffer);
    for (u32 index = 0; index < count * 256; ++index) {
        if (index % 256 == 0 && !wait_drq()) { return result::timeout; }
        out_word(data_port, source[index]);
    }
    return wait_not_busy() ? result::none : result::io;
}

result sync() {
    if (!device_present) { return result::no_device; }
    out_byte(command_port, 0xe7);
    return wait_not_busy() ? result::none : result::timeout;
}
}
