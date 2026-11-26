// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"
#include "named_resource_data.hpp"
#if XOS_PUMPKIN_MOBIUS
#include <xos/execution.hpp>
#endif

namespace xos::user::pumpkin::native_login {
inline constexpr char holder_image[] = "pumpkin_holder";
inline constexpr char broker_image_name[] = "p2_sealed";
static_assert(sizeof(broker_image_name) <= sizeof(image_info{}.name));
enum class holder_mode { cycle, submit, resource, desktop };
enum class result : u8 {
    passed = 1, holder_start = 23, holder_discovery, holder_pair, enrollment, delivery_receipt, enrollment_readback,
    resource_access, revocation, holder_exit,
    broker_launch, broker_bootstrap, broker_grant, broker_cleanup, desktop_failed,
};

// Provision one account over the authenticated registrar, deliver its initial
// credential to the immutable holder, and check login, authorization and revoke.
result run(u32 image, u64 daemon, ipc_client& registrar, account_name account);
int holder_main(holder_mode mode = holder_mode::cycle);

}

#if XOS_PUMPKIN_USER_LOGIN
namespace xos::user::pumpkin::anchor_guest { struct pair; }
namespace xos::user::pumpkin::native_login {
struct named_read {
    named_resource_request selection{};
    named_resource_data data{};
};
struct desktop_session;
u8 enroll_user(ipc_client& registrar, account_name account, const anchor_guest::pair& proxy);
u8 login_user(u32 image, u64 daemon, ipc_client& registrar, account_name account, const anchor_guest::pair& proxy,
              u32 broker_image = 0, named_read* named = nullptr, const desktop_session* desktop = nullptr);
#if XOS_PUMPKIN_MOBIUS
struct desktop_session {
    u32 display_image;
    u32 compositor_image;
    execution::image_receipt executable;
};
#endif
bool revoke_user(ipc_client& registrar, account_name account);
}
#endif
