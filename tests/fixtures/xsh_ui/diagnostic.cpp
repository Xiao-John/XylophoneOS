// SPDX-License-Identifier: Apache-2.0
#include <xos/execution.hpp>
#include <xos/sdk.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    const char* argv[] = {"ui_data"};
    xos::sdk::spawn_options options{};
    for (unsigned i = 0; i < 20; ++i) {
        xos::execution::launch_diagnostic diagnostic{};
        const auto result = xos::execution::spawn_file_diagnosed("/bin/ui_data", 1, argv, options, diagnostic);
        if (result != xos::process_error_denied ||
            diagnostic.stage != xos::execution::launch_stage::create ||
            diagnostic.code != result) { return 31; }
        if (xos::execution::inspect("/bin/ui_data").kind != xos::execution::candidate_kind::executable) {
            return 32;
        }
    }
    xos::sdk::print("DIAG_CREATE_DENIED_CLEANUP=20\n");
    return 0;
}
