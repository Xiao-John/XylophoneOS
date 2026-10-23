#include <xos/sdk.hpp>
extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("[slow] waiting ticks\n");
    const auto start = xos::sdk::ticks();
    while (xos::sdk::ticks() - start < 30) { xos::sdk::yield(); }
    return -7;
}
