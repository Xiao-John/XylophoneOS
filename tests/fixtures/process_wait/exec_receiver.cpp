// SPDX-License-Identifier: Apache-2.0
// This receiver uses the existing complete newlib CRT/FD startup contract;
// wait-any itself is a native SDK call and keeps no child PID inventory.
#include <stdio.h>
#include <stdlib.h>
#include <xos/sdk.hpp>
int main(int argc, char** argv) {
    using namespace xos;
    if (argc != 2 || strtoull(argv[1], nullptr, 10) != sdk::pid()) return 94;
    process_status first{}, second{};
    if (sdk::wait_any(first) != 0 || sdk::wait_any(second) != 0) return 95;
    if (first.pid == second.pid || first.code + second.code != 123 ||
        first.outcome != process_outcome::exited || second.outcome != process_outcome::exited) return 96;
    if (sdk::wait_any(first, true) != process_error_denied) return 97;
    puts("WAIT_ANY_PASS exec-existing"); return 0;
}
