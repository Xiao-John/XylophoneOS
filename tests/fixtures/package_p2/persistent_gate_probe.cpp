// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
using namespace xos;
extern "C" int xos_user_main(const startup_info* startup) {
    const char* const* argv = reinterpret_cast<const char* const*>(startup->argv);
    const char* mode = startup->argc > 1 ? argv[1] : "normal";
    if (sdk::equal(mode, "normal")) { sdk::print("GATE_NORMAL\n"); return 0; }
    file::Client files;
    if (!files.init() || files.maintenance_acquire() != 0) { sdk::print("GATE_FAIL acquire\n"); return 1; }
    if (sdk::equal(mode, "keep")) { sdk::print("GATE_KEEP\n"); return 0; }
    if (sdk::equal(mode, "mark")) {
        if (files.mkdir("/var/lib/xypm/transaction") != 0 || files.sync() != 0) {
            sdk::print("GATE_FAIL mark\n"); return 4;
        }
        sdk::print("GATE_MARKED\n"); return 0;
    }
    if (!sdk::equal(mode, "clear")) { return 2; }
    if (files.remove("/var/lib/xypm/transaction") != 0 || files.sync() != 0) {
        sdk::print("GATE_FAIL clear\n"); return 3;
    }
    sdk::print("GATE_CLEARED\n"); return 0;
}
