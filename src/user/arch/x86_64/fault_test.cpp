#include <xos/abi_types.hpp>
namespace {
const char readonly[] = "protected";
xos::u8 non_executable[16];
}
extern "C" void provoke_user_fault(xos::u32 kind) {
    if (kind == 1) {
        *reinterpret_cast<volatile char*>(const_cast<char*>(readonly)) = 'x';
    } else if (kind == 2) {
        reinterpret_cast<void (*)()>(non_executable)();
    } else if (kind == 3) {
        __asm__ volatile("fldz");
    } else {
        (void)*reinterpret_cast<volatile xos::u64*>(0x100000);
    }
}
