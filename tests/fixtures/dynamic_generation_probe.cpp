// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_launch.hpp>
#include <xos/execution.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include "dynamic_roots.hpp"

namespace {
using namespace xos;
static_assert(dynamic_run_approved.count == 3);
dynamic::closure retained;

i64 inherit_authority(u64 child, void*) {
    return sdk::syscall(sys_process_authority, child,
                        static_cast<u64>(process_authority_mode::copy_from_caller));
}
u64 deadline() {
    const i64 now = sdk::syscall(sys_clock_monotonic);
    return now < 0 || static_cast<u64>(now) > 0x7fffffffffffffffULL - dynamic::startup_deadline_limit_ns
        ? 0 : static_cast<u64>(now) + dynamic::startup_deadline_limit_ns;
}
int fail(const char* phase, i64 result) {
    sdk::print("R2_PROBE_FAIL phase="); sdk::print(phase);
    sdk::print(" result="); sdk::signed_decimal(result); sdk::print("\n");
    return 1;
}
void passed(const char* phase) {
    sdk::print("R2_PROBE_PASS "); sdk::print(phase); sdk::print("\n");
}
bool state(u32 active, u64 sequence, u32 revoked) {
    dynamic::launch_policy current{};
    return dynamic::export_policy(current) == dynamic::error::none && current.count == 3 &&
        current.active == active && current.sequence == sequence && current.revoked == revoked;
}
i64 run(u32 slot) {
    const char* const arguments[]{dynamic_run_main_paths[slot], "basic"};
    const char* const environment[]{"DYNAMIC_ENV=verified"};
    sdk::spawn_options options{};
    options.prepare_child = inherit_authority;
    options.environment_count = 1;
    options.environment = environment;
    const auto candidate = execution::inspect(arguments[0]);
    if (candidate.kind != execution::candidate_kind::executable)
        return candidate.error ? candidate.error : process_error_state;
    execution::launch_diagnostic diagnostic{};
    execution::image_receipt receipt{};
    const i64 child = execution::spawn_file_diagnosed_receipt(arguments[0], 2, arguments,
                                                             options, diagnostic, receipt);
    if (child < 0) return child;
    process_status status{};
    const i64 waited = sdk::wait_flags(static_cast<u64>(child), status);
    if (waited) return waited;
    if (status.pid != static_cast<u64>(child) || status.outcome != process_outcome::exited)
        return process_error_state;
    return status.code;
}
launch::artifact artifact(u32 index) {
    launch::artifact result{};
    result.id = dynamic_run_approved.roots[index].root.id;
    for (u32 i = 0; i < sizeof(result.sha256); ++i)
        result.sha256[i] = dynamic_run_approved.roots[index].root.sha256[i];
    return result;
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    auto error = dynamic::install(dynamic_run_approved, deadline());
    if (error != dynamic::error::none || !state(0, 1, 0))
        return fail("configure", static_cast<i64>(error));
    i64 result = run(0);
    if (result) return fail("initial_launch", result);
    passed("initial_generation_0");

    error = dynamic::acquire_index(0, deadline(), retained);
    if (error != dynamic::error::none) return fail("retain_old_pin", static_cast<i64>(error));
    const u32 old_handle = retained.pins[2].handle, old_inode = retained.pins[2].inode;
    error = dynamic::activate(1, 1, deadline());
    if (error != dynamic::error::none || !state(1, 2, 0))
        return fail("activate_1", static_cast<i64>(error));
    u8 header[4]{};
    if (retained.pins[2].handle != old_handle || retained.pins[2].inode != old_inode ||
        !dynamic::pin_read(&retained.pins[2], 0, header, sizeof(header)) ||
        header[0] != 0x7f || header[1] != 'E' || header[2] != 'L' || header[3] != 'F' ||
        retained.ticket.root.id != dynamic_run_approved.roots[0].root.id)
        return fail("old_generation_pin", retained.pins[2].native_error);
    result = dynamic::release(retained);
    if (result || dynamic::release(retained)) return fail("release_old_pin", result);
    result = run(1);
    if (result) return fail("generation_1_launch", result);
    passed("activate_1_preserves_old_pin");

    error = dynamic::activate(0, 1, deadline());
    if (error != dynamic::error::stale || !state(1, 2, 0))
        return fail("stale_activation", static_cast<i64>(error));
    passed("stale_sequence_rejected");

    error = dynamic::activate(2, 2, deadline());
    if (error == dynamic::error::none || !state(1, 2, 0))
        return fail("failed_activation_changed_state", static_cast<i64>(error));
    result = run(1);
    if (result) return fail("old_launch_after_failure", result);
    passed("failed_activation_preserves_old");

    error = dynamic::activate(0, 2, deadline());
    if (error != dynamic::error::none || !state(0, 3, 0))
        return fail("rollback_0", static_cast<i64>(error));
    result = run(0);
    if (result) return fail("rollback_launch", result);
    passed("rollback_0");

    error = dynamic::revoke(1, 2);
    if (error != dynamic::error::stale || !state(0, 3, 0))
        return fail("stale_revocation", static_cast<i64>(error));
    error = dynamic::revoke(1, 3);
    if (error != dynamic::error::none || !state(0, 4, 2))
        return fail("revoke_1", static_cast<i64>(error));
    const launch::artifact empty{}, zero = artifact(0), one = artifact(1);
    if (dynamic::admission(nullptr, sdk::pid(), zero, one, deadline()) != process_error_denied ||
        dynamic::admission(nullptr, sdk::pid(), empty, zero, deadline()))
        return fail("current_admission", process_error_state);
    error = dynamic::activate(1, 4, deadline());
    if (error != dynamic::error::revoked || !state(0, 4, 2))
        return fail("revoked_activation", static_cast<i64>(error));
    passed("revocation_blocks_future_admission");

    error = dynamic::revoke(0, 4);
    if (error != dynamic::error::none || !state(dynamic::activation_max_generations, 5, 3))
        return fail("revoke_active", static_cast<i64>(error));
    error = dynamic::acquire(dynamic_run_main_paths[0], deadline(), retained);
    if (error != dynamic::error::revoked || retained.live || retained.quarantined ||
        dynamic::admission(nullptr, sdk::pid(), empty, zero, deadline()) != process_error_denied)
        return fail("revoked_capture", static_cast<i64>(error));
    passed("active_revocation_blocks_capture");
    sdk::print("R2_PROBE_OK cases=7 sequence=5 revoked=3\n");
    return 0;
}
