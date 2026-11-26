// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "disk_test_store.hpp"

namespace xos::user::pumpkin {

#ifdef XOS_PUMPKIN_DEPLOYMENT_REALM
inline constexpr nonce anchored_installation_realm{{XOS_PUMPKIN_DEPLOYMENT_REALM}};
#else
inline constexpr nonce anchored_installation_realm = disk_test_realm;
#endif

}
