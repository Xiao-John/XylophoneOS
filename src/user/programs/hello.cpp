#include <xos/sdk.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("hello from file\n");
    return 0;
}
