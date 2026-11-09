// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/interactium_abi.hpp>

namespace xos::interactium {

inline constexpr i32 transport_again = -3;
inline constexpr i32 transport_closed = -19;

// The endpoint adapter implements this narrow interface. Authentication is
// supplied out of band by the endpoint and never taken from wire_header.
class session_transport {
public:
    ~session_transport() = default;
    virtual u64 authenticated_owner() const = 0;
    virtual i32 receive(u8* buffer, u32 capacity, u32& size) = 0;
    virtual i32 send(const u8* buffer, u32 size) = 0;
    virtual bool closed() const = 0;
    virtual bool reply_drained() const = 0;
    virtual void close() {}
};

} // namespace xos::interactium
