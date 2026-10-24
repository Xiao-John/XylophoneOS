// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <xos/process_abi.hpp>

extern "C" int xos_libc_init(const xos::startup_info* startup);
extern "C" void xos_libc_finish();
extern "C" int xos_cpp_runtime_init();
extern "C" int xos_libc_main_entry(const xos::startup_info* startup);
extern "C" char** environ;
