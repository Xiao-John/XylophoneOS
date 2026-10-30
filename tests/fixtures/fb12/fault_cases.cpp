// SPDX-License-Identifier: Apache-2.0
// Guest-only deterministic FB1 exception and cancellation fixture.
#include <xos/sdk.hpp>
extern "C" int xos_user_main(const xos::startup_info* info) {
    if (info == nullptr || info->argc < 2) return 2;
    const auto* args = reinterpret_cast<const char* const*>(info->argv);
    if (xos::sdk::equal(args[1], "ud")) {
        xos::sdk::print("FB12_UD\n");
        __asm__ volatile("ud2");
    }
    if (xos::sdk::equal(args[1], "divide")) {
        xos::sdk::print("FB12_DIVIDE\n");
        __asm__ volatile("xor %%rdx, %%rdx; mov $1, %%rax; xor %%rcx, %%rcx; div %%rcx"
                         ::: "rax", "rcx", "rdx", "cc");
    }
    if (xos::sdk::equal(args[1], "spin")) {
        xos::sdk::print("FB12_SPIN\n");
        for (;;) xos::sdk::yield();
    }
    return 3;
}
