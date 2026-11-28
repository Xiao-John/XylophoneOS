// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#ifndef EXEC_MARKER
#define EXEC_MARKER 0
#endif
#if EXEC_MARKER
struct marker_record { xos::u64 magic; xos::u32 version, size; };
[[gnu::used, gnu::section(".xos.exec")]] const marker_record marker{
    xos::exec_image_abi_magic, EXEC_MARKER, sizeof(marker_record)};
#endif

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (!startup || startup->magic != startup_magic || startup->argc != 2 ||
        startup->version != (EXEC_MARKER == 3 ? 3u : 2u)) return 31;
    const auto* arguments = reinterpret_cast<const char* const*>(startup->argv);
    if (!arguments || !arguments[1]) return 32;
    if (arguments[1][0] == 'p') {
        char input[4]{};
        if (sdk::read(0, input, sizeof(input)) != 4 || input[0] != 'D' || input[1] != 'A'
            || input[2] != 'T' || input[3] != 'A') return 33;
        if (sdk::write(1, "OUT", 3) != 3 || sdk::write(2, "ERR", 3) != 3) return 34;
    } else if (arguments[1][0] == 'c') {
        char input = 0;
        if (sdk::read(0, &input, 1) != process_error_denied) return 35;
        sdk::print("STATIC_STDIO_CHILD closed_stdin\n");
    } else {
        sdk::print(EXEC_MARKER == 3 ? "STATIC_STDIO_CHILD v3\n" : "STATIC_STDIO_CHILD raw\n");
    }
    return 0;
}
