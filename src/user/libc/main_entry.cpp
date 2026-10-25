// SPDX-License-Identifier: Apache-2.0
#include <xos/libc_runtime.hpp>
#include <stdlib.h>
#include <xos/sdk.hpp>

extern "C" int main(int argc, char** argv, char** envp);
extern "C" int xos_thread_runtime_init() __attribute__((weak));

extern "C" int xos_libc_main_entry(const xos::startup_info* startup) {
    if (xos_thread_runtime_init != nullptr && xos_thread_runtime_init() != 0) {
        xos::sdk::exit(127);
    }
    if (xos_libc_init(startup) != 0) { exit(127); }
    if (xos_cpp_runtime_init() != 0) { exit(127); }
    const int argc = startup == nullptr ? 0 : static_cast<int>(startup->argc);
    char** argv = startup == nullptr ? nullptr : reinterpret_cast<char**>(startup->argv);
    exit(main(argc, argv, environ));
}
