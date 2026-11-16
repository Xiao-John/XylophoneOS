// SPDX-License-Identifier: Apache-2.0
#include <cstddef>
#include <xos/process_abi.hpp>
#include "xos_cpu_time.h"
static_assert(sizeof(xos_cpu_time) == sizeof(xos::process_cpu_time));
#define SAME_OFFSET(field) static_assert(offsetof(xos_cpu_time, field) == offsetof(xos::process_cpu_time, field))
SAME_OFFSET(version); SAME_OFFSET(size); SAME_OFFSET(user_ns); SAME_OFFSET(system_ns);
SAME_OFFSET(child_user_ns); SAME_OFFSET(child_system_ns); SAME_OFFSET(thread_user_ns);
SAME_OFFSET(thread_system_ns); SAME_OFFSET(elapsed_ns); SAME_OFFSET(resolution_ns);
int main() {}
