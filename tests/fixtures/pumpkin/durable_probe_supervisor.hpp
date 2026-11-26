// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../../../src/user/services/files_private_broker.hpp"

namespace xos::user::pumpkin::durable_probe {

using grant_function = bool (*)(u64, user::files_private_storage::access,
                               user::files_private_storage::grant_reply&);
void run(u32 image, grant_function grant, const char* mode);
#if XOS_PUMPKIN_ANCHORED_PROBE
int run_anchored(u32 image, u32 proxy_image, grant_function grant);
#endif

}
