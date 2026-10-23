#include <xos/platform.hpp>

namespace xos::arch {
const char* name() { return "x86_64"; }
[[noreturn]] void halt() {
    __asm__ volatile("cli" : : : "memory");
    for (;;) {
        __asm__ volatile("hlt" : : : "memory");
    }
}
}
