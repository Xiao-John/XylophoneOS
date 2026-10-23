#include <xos/sdk.hpp>
extern "C" int xos_user_main(const xos::startup_info*) {
    xos::sdk::print("[echo] input> ");
    for (xos::u32 i = 0; i < 64;) {
        char byte;
        const auto received = xos::sdk::read(0, &byte, 1);
        if (received == xos::process_error_would_block) { xos::sdk::yield(); continue; }
        if (received <= 0) { return 1; }
        if (byte == '\r' || byte == '\n') { xos::sdk::print("\n[echo] done\n"); return 0; }
        (void)xos::sdk::write(1, &byte, 1); ++i;
    }
    return 2;
}
