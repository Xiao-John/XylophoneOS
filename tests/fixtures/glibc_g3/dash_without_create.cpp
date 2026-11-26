// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>

namespace {
xos::i64 clear_create(xos::u64 child, void*) {
    return xos::sdk::syscall(xos::sys_process_authority, child,
                             static_cast<xos::u64>(xos::process_authority_mode::clear));
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    if (startup->argc != 2) { return 90; }
    const auto original = reinterpret_cast<const char* const*>(startup->argv);
    const char* arguments[] = {"/bin/dash_glibc", original[1]};
    xos::sdk::spawn_options options{};
    options.prepare_child = clear_create;
    const auto child = xos::sdk::spawn_file_options(arguments[0], 2, arguments, options);
    if (child < 0) { return 91; }
    xos::process_status status{};
    if (xos::sdk::wait(static_cast<xos::u64>(child), status) != 0 ||
        status.outcome != xos::process_outcome::exited) { return 92; }
    return static_cast<int>(status.code);
}
