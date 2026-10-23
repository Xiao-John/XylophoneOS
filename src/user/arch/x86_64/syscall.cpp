#include <xos/sdk.hpp>
namespace xos::sdk {
u16 target_elf_machine() { return 62; }
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    u64 result;
    __asm__ volatile("int $0x80" : "=a"(result) : "a"(number), "D"(first), "S"(second),
                     "d"(third) : "memory", "cc");
    return static_cast<i64>(result);
}
[[noreturn]] void exit(i32 code) {
    (void)syscall(2, static_cast<u64>(static_cast<i64>(code)));
    for (;;) { __asm__ volatile("ud2"); }
}
}
