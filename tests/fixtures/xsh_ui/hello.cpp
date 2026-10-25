/* SPDX-License-Identifier: Apache-2.0 */
#include <xos/sdk.hpp>

extern "C" int xos_user_main(const xos::startup_info*) {
    const xos::i64 result = xos::sdk::syscall(36, 0);
    xos::sdk::print("TRACE_DENIED=");
    xos::sdk::signed_decimal(result);
    xos::sdk::print("\n");
    xos::sdk::print("xsh_ui_path_candidate_ran\n");
    return 0;
}
