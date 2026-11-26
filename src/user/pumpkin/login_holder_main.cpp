// SPDX-License-Identifier: Apache-2.0
#include "native_login.hpp"

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos::user::pumpkin::native_login;
    if (startup == nullptr || startup->magic != xos::startup_magic) return 10;
#if XOS_PUMPKIN_USER_LOGIN
    if (startup->argc == 2) {
        const auto* args = reinterpret_cast<const char* const*>(startup->argv);
        if (xos::sdk::equal(args[1], "submit")) return holder_main(holder_mode::submit);
#if XOS_PUMPKIN_MOBIUS
        if (xos::sdk::equal(args[1], "desktop")) return holder_main(holder_mode::desktop);
#endif
#if XOS_PUMPKIN_USER_RESOURCE
        if (xos::sdk::equal(args[1], "resource")) return holder_main(holder_mode::resource);
#endif
    }
#endif
    return startup->argc == 1 ? holder_main() : 10;
}
