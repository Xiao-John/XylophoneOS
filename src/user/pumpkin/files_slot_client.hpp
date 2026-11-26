// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "disk_test_store.hpp"
#include "../services/files_private_broker.hpp"

namespace xos::user::pumpkin {

class files_slot_client {
public:
    files_slot_client() = default;
    files_slot_client(const files_slot_client&) = delete;
    files_slot_client& operator=(const files_slot_client&) = delete;
    ~files_slot_client();

    bool bind_bootstrap();
    bool live() const;
    test_slot_io io();

private:
    bool read(u32 slot, u8 (&bytes)[user::files_private_storage::slot_bytes]);
    bool write(u32 slot, const u8 (&bytes)[user::files_private_storage::slot_bytes]);
    bool call(user::files_private_storage::request& request,
              user::files_private_storage::response& response);

    ipc_channel channel_{};
    u64 sequence_ = 0;
};

}
