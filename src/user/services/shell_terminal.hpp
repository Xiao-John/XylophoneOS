// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::user::shell_terminal {
// Supervisor is single-threaded. This is not an application TTY session.
i64 start(const char* path);
}
