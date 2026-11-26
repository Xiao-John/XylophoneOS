// SPDX-License-Identifier: Apache-2.0
#include "native_login.hpp"

extern "C" int xos_user_main(const xos::startup_info* startup) {
    if (startup == nullptr || startup->magic != xos::startup_magic) return 10;
#if XOS_PUMPKIN_USER_LOGIN
    if (startup->argc == 2) {
        const auto* args = reinterpret_cast<const char* const*>(startup->argv);
        if (xos::sdk::equal(args[1], "submit")) return xos::user::pumpkin::native_login::holder_main(true);
    }
#endif
    return startup->argc == 1 ? xos::user::pumpkin::native_login::holder_main() : 10;
}
