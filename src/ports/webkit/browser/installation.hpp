// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/execution.hpp>
#include <xos/process_budget_abi.hpp>

namespace xos::clarke {
struct executable {
    const char* path;
    execution::image_receipt receipt;
    process_budget_vector limits;
};
struct installation { executable ui, network, renderer; };
}
