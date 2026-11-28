// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "xypm_distribution.hpp"
#include <xos/distribution_startup.hpp>

namespace xypm_distribution {
int command(const char* directory, const char* lock, const char* parent_name,
            bool install, const xypm_repository_auth::bootstrap& trust,
            const xos::u8 (&sdk_identity)[32], bool (*canonical_path)(const char*));
}
