// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/abi_types.hpp>

namespace xos::user::pumpkin {

inline constexpr u64 connection_lifetime_ns = 30ull * 60 * 1'000'000'000;
inline constexpr u64 desktop_backing_grace_ns = 60ull * 1'000'000'000;

}
