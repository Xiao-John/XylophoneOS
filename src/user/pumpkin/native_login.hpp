// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"

namespace xos::user::pumpkin::native_login {
inline constexpr char holder_image[] = "pumpkin_holder";
enum class result : u8 {
    passed = 1, holder_start = 23, holder_discovery, holder_pair, enrollment, delivery_receipt, enrollment_readback,
    resource_access, revocation, holder_exit,
};

// Provision one account over the authenticated registrar, deliver its initial
// credential to the immutable holder, and check login, authorization and revoke.
result run(u32 image, u64 daemon, ipc_client& registrar, account_name account);
int holder_main();
}
