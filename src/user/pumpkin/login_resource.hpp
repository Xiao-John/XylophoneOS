// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "native_ipc.hpp"
#include "sealed_blob.hpp"

namespace xos::user::pumpkin {
inline constexpr u32 login_resource_value = 0x31474f4c; // LOG1

class login_resource {
public:
    status invoke(service_core& core, const connection_id& connection, const ipc_channel& channel,
                  bool registrar, const wire_request& request, u64 now, wire_reply& reply);

private:
    file::client files_;
    sealed_blob object_{files_};
    ipc_channel granted_{};
    u64 holder_ = 0;
};
}
