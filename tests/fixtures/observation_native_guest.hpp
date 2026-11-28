// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace xos::test_observation_native {
[[noreturn]] inline void fail(const char* label, i64 code = 0) {
    sdk::print("OBS_NATIVE_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(code); sdk::print("\n"); sdk::exit(91);
}
inline void require(bool good, const char* label, i64 code = 0) { if (!good) fail(label, code); }
inline u64 now() {
    const i64 value = sdk::syscall(sys_clock_monotonic);
    require(value >= 0, "clock", value); return static_cast<u64>(value);
}
inline observe_native::request request(observe_native::query kind, u64 target = 0) {
    return {observe_native::version, sizeof(observe_native::request), kind, 0,
            target, 0, 0, now() + 2'000'000'000ULL};
}
inline bool zero(const observe_native::snapshot& value) {
    const observe_native::snapshot empty{};
    return !__builtin_memcmp(&value, &empty, sizeof(value));
}
inline observe_native::snapshot own() {
    auto input = request(observe_native::query::process); observe_native::snapshot output{};
    const auto result = sdk::observe(input, output);
    require(result == observe_native::result::ok, "self", static_cast<i64>(result)); return output;
}
inline void run_native_checks() {
    using namespace observe_native;
    const auto self = own();
    require(self.version == version && self.size == sizeof(self) && self.pid == sdk::pid() &&
            self.image_generation && self.threads && self.threads <= thread_max_per_process &&
            self.blocked_threads < self.threads && self.process_state == state::running,
            "self-shape");
    auto input = request(query::resources); snapshot output{};
    require(sdk::observe(input, output) == result::ok && output.pid == self.pid &&
            output.pages && output.pages <= output.page_limit &&
            output.owned_channels <= output.channel_limit && output.channel_limit == ipc_max_owned_channels &&
            output.owned_names <= output.name_limit && output.name_limit == ipc_max_owned_names &&
            output.pipe_references <= output.pipe_reference_limit, "resource-bounds");
    sdk::print("OBS_NATIVE_SELF_PASS\n");
    require(self.parent_pid && self.parent_pid != self.pid, "ordinary-child-parent");
    input = request(query::process, self.parent_pid);
    require(sdk::observe(input, output) == result::denied && zero(output), "parent-denied");
    input = request(query::process);
    input.expected_pid = self.pid; input.expected_generation = self.image_generation == 1 ? 2 : 1;
    require(sdk::observe(input, output) == result::stale && zero(output), "stale-image");
    sdk::print("OBS_NATIVE_SCOPE_PASS\n");
    input = request(query::process); input.version = version + 1;
    require(sdk::observe(input, output) == result::invalid && zero(output), "wrong-version");
    input = request(query::process); --input.size;
    require(sdk::observe(input, output) == result::invalid && zero(output), "wrong-size");
    input = request(query::process); input.reserved = 1;
    require(sdk::observe(input, output) == result::invalid && zero(output), "reserved");
    input = request(query::process); input.kind = static_cast<query>(4);
    require(sdk::observe(input, output) == result::invalid && zero(output), "wrong-kind");
    input = request(query::process); input.deadline_ns = 0;
    require(sdk::observe(input, output) == result::invalid && zero(output), "zero-deadline");
    input.deadline_ns = ~u64{0};
    require(sdk::observe(input, output) == result::invalid && zero(output), "infinite-deadline");
    input = request(query::process);
    require(sdk::syscall(sys_observe, reinterpret_cast<u64>(&input),
                        reinterpret_cast<u64>(&output), 1) == static_cast<i64>(result::invalid) && zero(output),
            "reserved-syscall-argument");
    sdk::print("OBS_NATIVE_FORMAT_PASS\n");
    input = request(query::process); input.deadline_ns = now();
    require(input.deadline_ns != 0, "boot-clock-started");
    require(sdk::observe(input, output) == result::deadline && zero(output), "expired-deadline");
    sdk::print("OBS_NATIVE_DEADLINE_PASS\n");
}
}
