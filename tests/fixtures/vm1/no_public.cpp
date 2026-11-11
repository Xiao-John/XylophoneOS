// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
struct request { xos::u32 version,size,operation,flags; xos::u64 address,length,alignment; xos::u32 protection,reserved0; xos::u64 reserved1,reserved2; };
extern "C" int xos_user_main(const xos::startup_info*) {
    request value{1,64,1,1,0x100000000000ull,4096,4096,0,0,0,0};
    if (xos::sdk::syscall(67,reinterpret_cast<xos::u64>(&value),0,0) != -2) return 1;
    xos::sdk::print("VM1_DISABLED_PASS\n");
    return 0;
}
