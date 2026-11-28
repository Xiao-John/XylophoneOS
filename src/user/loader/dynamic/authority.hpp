// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/dynamic_launch.hpp>

namespace xos::dynamic {
error restore_authority(const catalog::authority& authority, const launch::artifact& owner = {});
i64 authority_admission(const launch::artifact& current, const launch::artifact& requested, u64 deadline);
}
