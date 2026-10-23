#include <xos/sdk.hpp>
extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("[spin] alive\n");
    for (;;) { (void)xos::sdk::ticks(); }
}
