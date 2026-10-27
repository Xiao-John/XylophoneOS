// SPDX-License-Identifier: Apache-2.0
#include <xos/platform.hpp>
#include <xos/process_abi.hpp>
#include "arch/x86_64/io.hpp"

namespace xos::platform {
namespace {
using arch::in_byte;
using arch::out_byte;
constexpr u16 cmos_index = 0x70;
constexpr u16 cmos_data = 0x71;
constexpr u8 reg_seconds = 0x00;
constexpr u8 reg_minutes = 0x02;
constexpr u8 reg_hours = 0x04;
constexpr u8 reg_weekday = 0x06;
constexpr u8 reg_day = 0x07;
constexpr u8 reg_month = 0x08;
constexpr u8 reg_year = 0x09;
constexpr u8 reg_status_a = 0x0a;
constexpr u8 reg_status_b = 0x0b;
constexpr u8 reg_status_d = 0x0d;
constexpr u8 reg_century = 0x32;
constexpr u8 uip = 0x80;
constexpr u8 valid_ram = 0x80;
constexpr u8 binary_mode = 0x04;
constexpr u8 hour_24 = 0x02;

struct rtc_sample { u8 sec, min, hour, day, month, year, century, status_b; };
bool clock_valid;
u64 base_epoch_ns;
u64 base_monotonic_ns;

u8 read_register(u8 reg) {
    // Keep NMI enabled while selecting a CMOS register.
    out_byte(cmos_index, reg);
    return in_byte(cmos_data);
}

bool read_sample(rtc_sample& sample) {
    for (u32 attempt = 0; attempt < 8; ++attempt) {
        if ((read_register(reg_status_a) & uip) != 0) { continue; }
        rtc_sample first{};
        first.sec = read_register(reg_seconds);
        first.min = read_register(reg_minutes);
        first.hour = read_register(reg_hours);
        (void)read_register(reg_weekday);
        first.day = read_register(reg_day);
        first.month = read_register(reg_month);
        first.year = read_register(reg_year);
        first.century = read_register(reg_century);
        first.status_b = read_register(reg_status_b);
        if ((read_register(reg_status_a) & uip) != 0) { continue; }
        rtc_sample second{};
        second.sec = read_register(reg_seconds);
        second.min = read_register(reg_minutes);
        second.hour = read_register(reg_hours);
        (void)read_register(reg_weekday);
        second.day = read_register(reg_day);
        second.month = read_register(reg_month);
        second.year = read_register(reg_year);
        second.century = read_register(reg_century);
        second.status_b = read_register(reg_status_b);
        if ((read_register(reg_status_a) & uip) != 0) { continue; }
        if (first.sec != second.sec || first.min != second.min || first.hour != second.hour ||
            first.day != second.day || first.month != second.month || first.year != second.year ||
            first.century != second.century || first.status_b != second.status_b) { continue; }
        sample = second;
        return true;
    }
    return false;
}

bool decode(u8 value, bool binary, u8& result) {
    if (binary) { result = value; return true; }
    const u8 low = value & 0x0f;
    const u8 high = (value >> 4) & 0x0f;
    if (low > 9 || high > 9) { return false; }
    result = static_cast<u8>(high * 10 + low);
    return true;
}

bool leap_year(u32 year) { return year % 4 == 0 && (year % 100 != 0 || year % 400 == 0); }

bool sample_epoch(const rtc_sample& s, u64& epoch_seconds) {
    if ((read_register(reg_status_d) & valid_ram) == 0) { return false; }
    const bool binary = (s.status_b & binary_mode) != 0;
    const bool is_24_hour = (s.status_b & hour_24) != 0;
    u8 sec, min, hour, day, month, year2, century;
    const bool pm = (s.hour & 0x80) != 0;
    if (!decode(s.sec, binary, sec) || !decode(s.min, binary, min) ||
        !decode(static_cast<u8>(s.hour & 0x7f), binary, hour) ||
        !decode(s.day, binary, day) || !decode(s.month, binary, month) ||
        !decode(s.year, binary, year2) || !decode(s.century, binary, century)) { return false; }
    if (!is_24_hour) {
        if (hour == 0 || hour > 12) { return false; }
        hour = static_cast<u8>((hour % 12) + (pm ? 12 : 0));
    }
    if (sec > 59 || min > 59 || hour > 23 || month < 1 || month > 12 || year2 > 99) { return false; }
    // QEMU and the supported PC profile provide the century byte. A zero or
    // nonsensical century is rejected rather than silently inventing a date.
    const u32 year = static_cast<u32>(century) * 100 + year2;
    if (year < 1970 || year > 9999) { return false; }
    constexpr u8 month_days[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    const u8 max_day = static_cast<u8>(month_days[month - 1] + ((month == 2 && leap_year(year)) ? 1 : 0));
    if (day < 1 || day > max_day) { return false; }
    u64 days = 0;
    for (u32 y = 1970; y < year; ++y) { days += leap_year(y) ? 366 : 365; }
    for (u32 m = 1; m < month; ++m) {
        days += month_days[m - 1] + ((m == 2 && leap_year(year)) ? 1 : 0);
    }
    days += day - 1;
    epoch_seconds = days * 86400 + static_cast<u64>(hour) * 3600 + static_cast<u64>(min) * 60 + sec;
    return true;
}
}

bool realtime_clock_init(u64 monotonic_ns) {
    clock_valid = false;
    rtc_sample sample{};
    u64 seconds = 0;
    if (!read_sample(sample) || !sample_epoch(sample, seconds) ||
        seconds > (~u64{0} / 1000000000ull)) { return false; }
    base_epoch_ns = seconds * 1000000000ull;
    base_monotonic_ns = monotonic_ns;
    clock_valid = true;
    return true;
}

i64 realtime_clock_ns(u64 monotonic_ns) {
    if (!clock_valid) { return realtime_error_io; }
    const u64 elapsed = monotonic_ns >= base_monotonic_ns ? monotonic_ns - base_monotonic_ns : 0;
    if (base_epoch_ns > static_cast<u64>(0x7fffffffffffffffll) - elapsed) { return realtime_error_io; }
    return static_cast<i64>(base_epoch_ns + elapsed);
}
}
