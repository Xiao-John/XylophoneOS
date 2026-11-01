// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::user::shell_terminal {
// Supervisor is single-threaded. prepare_application is called while the
// child is still building; finish_application is required after wait or a
// failed spawn following a successful prepare.
i64 start(const char* path);
i64 prepare_application(u64 child, void* context);
const u32* application_send_handle();
i64 finish_application();
i64 stop();
}
