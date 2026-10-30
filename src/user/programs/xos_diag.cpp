// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/execution.hpp>
#include "fault_bundle.hpp"

using namespace xos;
using namespace xos::sdk;

extern "C" int xos_user_main(const startup_info* startup) {
    const auto argv = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc < 2) { print("usage: xos-diag PROGRAM [ARG...]\n", 2); return 2; }
    const auto candidate = execution::resolve(argv[1], "/usr/bin:/bin:/");
    if (candidate.kind != execution::candidate_kind::executable) {
        print("xos-diag: cannot resolve program\n", 2); return 127;
    }
    const char* const environment[] = {"PATH=/usr/bin:/bin:/", nullptr};
    spawn_options options{};
    options.environment = environment; options.environment_count = 1;
    execution::launch_diagnostic diagnostic{};
    execution::image_receipt receipt{};
    const auto child = execution::spawn_file_diagnosed_receipt(candidate.path, startup->argc - 1,
                                                                 argv + 1, options, diagnostic, receipt);
    if (child < 0) { print("xos-diag: launch error=", 2); signed_decimal(child); print("\n", 2); return 126; }
    process_status status{};
    const auto waited = wait(static_cast<u64>(child), status);
    if (waited < 0) { print("xos-diag: wait failed\n", 2); return 125; }
    print("[xos-diag] kind=");
    if (status.outcome == process_outcome::exited) {
        print("exited code="); signed_decimal(status.code); print("\n");
        return static_cast<int>(static_cast<u64>(status.code) & 255);
    }
    if (status.outcome == process_outcome::faulted) {
        print("faulted vector="); decimal(status.vector); print("\n");
        if (!fault_bundle::save(status, receipt)) print("[fault-bundle] not saved; result unknown\n");
        return 128;
    }
    print("killed\n"); return 128;
}
