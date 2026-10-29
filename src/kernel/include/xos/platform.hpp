#pragma once
#include <xos/types.hpp>

// Implemented by the selected platform; common kernel code knows no ports,
// firmware interrupt numbers, register names, or device addresses.
namespace xos::platform {
void debug_init();
void debug_graphics(bool active);
bool debug_write(const char* text);
i64 debug_write_bytes(const u8* bytes, usize length);
// Before IRQ setup the debug console polls; afterwards the input queue is IRQ-fed.
// Caller must serialize with the receive interrupt.
int debug_read();
int debug_peek();
void debug_input_enable();
void debug_input_irq();
u64 debug_input_dropped();
// Hardware overrun observations; one observation may represent several bytes.
u64 debug_input_overruns();
// PC wall clock: snapshot UTC RTC at boot, then advance it from monotonic ticks.
bool realtime_clock_init(u64 monotonic_ns);
i64 realtime_clock_ns(u64 monotonic_ns);
}
namespace xos::arch {
const char* name();
[[noreturn]] void halt();
}
