// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "transport.hpp"
#include <xos/process_abi.hpp>

namespace xos::interactium {

class ipc_session_transport final : public session_transport {
    ipc_channel channel_{};

public:
    ipc_session_transport() = default;
    explicit ipc_session_transport(ipc_channel channel) : channel_(channel) {}
    void bind(ipc_channel channel) { channel_ = channel; }

    u64 authenticated_owner() const override;
    i32 receive(u8* buffer, u32 capacity, u32& size) override;
    i32 send(const u8* buffer, u32 size) override;
    bool closed() const override;
    void close() override;
};

} // namespace xos::interactium
