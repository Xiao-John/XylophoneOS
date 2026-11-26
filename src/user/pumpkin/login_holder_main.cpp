// SPDX-License-Identifier: Apache-2.0
#include "native_login.hpp"

extern "C" int xos_user_main(const xos::startup_info* startup) {
    return startup != nullptr && startup->magic == xos::startup_magic && startup->argc == 1
        ? xos::user::pumpkin::native_login::holder_main() : 10;
}
