// SPDX-License-Identifier: Apache-2.0
#include <xos/launch_control.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
constexpr const char* image = "/bin/launch.elf";
[[noreturn]] void fail(const char* label, i64 value = 0) {
    sdk::print("LAUNCH_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(value); sdk::print("\n"); sdk::exit(91);
}
void require(bool good, const char* label, i64 value = 0) { if (!good) fail(label, value); }
u64 now() {
    const i64 value = sdk::syscall(sys_clock_monotonic);
    require(value >= 0, "clock", value); return static_cast<u64>(value);
}
void sleep_to(u64 deadline) { require(!sdk::syscall(sys_sleep_until, deadline), "sleep"); }
launch::artifact root(u64 id) {
    launch::artifact value{}; value.id = id;
    for (u32 i = 0; i < 32; ++i) value.sha256[i] = static_cast<u8>(id * 17 + i);
    return value;
}
void encode(const launch::descriptor& value, char* text) {
    constexpr char digits[] = "0123456789abcdef";
    const auto* bytes = reinterpret_cast<const u8*>(&value);
    for (u32 i = 0; i < sizeof(value); ++i) {
        text[2 * i] = digits[bytes[i] >> 4]; text[2 * i + 1] = digits[bytes[i] & 15];
    }
    text[2 * sizeof(value)] = 0;
}
launch::descriptor decode(const char* text) {
    require(sdk::length(text) == 2 * sizeof(launch::descriptor), "descriptor-hex-length");
    launch::descriptor value{}; auto* bytes = reinterpret_cast<u8*>(&value);
    for (u32 i = 0; i < sizeof(value); ++i) {
        u32 byte = 0;
        for (u32 j = 0; j < 2; ++j) {
            const char c = text[2 * i + j];
            require((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'), "descriptor-hex");
            byte = byte * 16 + static_cast<u32>(c <= '9' ? c - '0' : c - 'a' + 10);
        }
        bytes[i] = static_cast<u8>(byte);
    }
    return value;
}
launch::descriptor initial_descriptor() {
    const u64 deadline = now() + 10'000'000'000ULL;
    channel_info in{}, out{};
    for (u32 i = 0; i < 2; ++i) {
        channel_info info{}; require(!sdk::channel_get(i, info), "initial-channel");
        if (info.rights == channel_receive) in = info;
        else if (info.rights == channel_send) out = info;
        else fail("initial-direction");
    }
    require(in.handle && out.handle && in.peer_pid == out.peer_pid &&
            in.controller_pid == in.peer_pid && out.controller_pid == in.peer_pid, "initial-identity");
    require(!sdk::channel_wait(in.handle, deadline), "initial-wait");
    launch::descriptor value{};
    const i64 received = sdk::ipc_recv(in.handle, &value, sizeof(value));
    require(received == sizeof(value) && value.child_pid == sdk::pid() && value.controller_pid == in.peer_pid &&
            value.ready_handle == out.handle && value.ack_handle == in.handle, "initial-descriptor", received);
    return value;
}
launch::message packet(const launch::descriptor& control, u32 type, u64 deadline, const launch::artifact& artifact) {
    return {XOS_LAUNCH_CONTROL_MAGIC, 1, sizeof(launch::message), type, 0, control.generation,
            control.nonce, control.child_pid, deadline, 0, artifact, {0, 0, 0}};
}
[[noreturn]] void replace(const launch::descriptor& pending, const char* mode) {
    char text[2 * sizeof(pending) + 1]{}; encode(pending, text);
    const char* args[]{image, "after", mode, text};
    const u32 kept[]{pending.ready_handle, pending.ack_handle};
    sdk::spawn_options options{};
    options.replace_image = true; options.exec_channel_count = 2; options.exec_channels = kept;
    fail("successful-exec-returned", sdk::spawn_file_options(image, 4, args, options));
}
int child(const char* mode) {
    const launch::descriptor active = initial_descriptor();
    if (sdk::equal(mode, "early-exit")) return 50;
    if (sdk::equal(mode, "timeout")) { sleep_to(active.deadline + 20'000'000); return 49; }
    if (sdk::equal(mode, "malformed")) {
        auto wrong = packet(active, XOS_LAUNCH_READY, active.deadline, root(1));
        wrong.reserved[0] = 1;
        require(!sdk::ipc_send(active.ready_handle, &wrong, sizeof(wrong)), "malformed-send");
        require(sdk::channel_wait(active.ack_handle, active.deadline) < 0, "malformed-close");
        return 51;
    }
    const i64 initial = launch::notify_ready(active, root(1));
    require(!initial, "initial-ready", initial);
    launch::descriptor pending{};
    if (sdk::equal(mode, "prepare-revoke")) {
        require(launch::prepare_exec(active, now() + 5'000'000'000ULL, root(2), pending) ==
                process_error_denied, "prepare-revoked");
        sdk::print("LAUNCH_PREPARE_REVOKED\n"); return 0;
    }
    if (sdk::equal(mode, "stale-allow")) {
        const u64 expires = now() + 300'000'000;
        const auto request = packet(active, XOS_LAUNCH_PREPARE, expires, root(2));
        require(!sdk::ipc_send(active.ready_handle, &request, sizeof(request)), "stale-allow-send");
        require(!sdk::channel_wait(active.ack_handle, expires), "stale-allow-queued");
        sleep_to(expires + 30'000'000);
        require(!launch::prepare_exec(active, now() + 5'000'000'000ULL, root(2), pending), "stale-allow-recovery");
        require(pending.generation == 3, "stale-allow-new-generation");
    } else if (sdk::equal(mode, "stale-cancel")) {
        require(!launch::prepare_exec(active, now() + 300'000'000, root(2), pending), "stale-cancel-prepare");
        const auto request = packet(pending, XOS_LAUNCH_CANCEL, pending.deadline, root(2));
        require(!sdk::ipc_send(pending.ready_handle, &request, sizeof(request)), "stale-cancel-send");
        require(!sdk::channel_wait(pending.ack_handle, pending.deadline), "stale-cancel-queued");
        sleep_to(pending.deadline + 30'000'000);
        require(!launch::prepare_exec(active, now() + 5'000'000'000ULL, root(2), pending), "stale-cancel-recovery");
        require(pending.generation == 3, "stale-cancel-new-generation");
    } else {
        const i64 prepared = launch::prepare_exec(active, now() + 5'000'000'000ULL, root(2), pending);
        require(!prepared, "prepare", prepared);
        if (sdk::equal(mode, "cancel")) {
            const char* missing[]{"/missing-launch-image"};
            sdk::spawn_options options{}; options.replace_image = true;
            const u32 kept[]{pending.ready_handle, pending.ack_handle};
            options.exec_channel_count = 2; options.exec_channels = kept;
            require(sdk::spawn_file_options(missing[0], 1, missing, options) < 0, "precommit-missing");
            require(sdk::pid() == active.child_pid, "precommit-same-pid");
            require(!launch::cancel_exec(pending, root(2)), "cancel-ack");
            require(!launch::prepare_exec(active, now() + 5'000'000'000ULL, root(2), pending), "prepare-after-cancel");
            require(pending.generation == 3, "cancel-no-generation-reuse");
        }
    }
    replace(pending, mode);
}
int after(const startup_info* startup, const char* mode, const char* encoded) {
    const auto control = decode(encoded);
    require(startup->version == 3 && sdk::pid() == control.child_pid && control.generation >= 2, "real-same-pid-exec");
    if (sdk::equal(mode, "entry-failure")) {
        require(!launch::notify_ready(control, root(2), -77, XOS_LAUNCH_PHASE_INITIALIZE), "failure-ack");
        return 47;
    }
    const i64 result = launch::notify_ready(control, root(2));
    if (sdk::equal(mode, "entry-revoke")) {
        require(result == process_error_denied, "entry-revoked", result); return 48;
    }
    require(!result, "successor-ready", result);
    sdk::print("LAUNCH_SAME_PID_EXEC "); sdk::decimal(sdk::pid()); sdk::print("\n");
    return 0;
}
struct policy {
    const char* mode;
    u32 requests = 0;
    u64 child = 0;
    launch::descriptor control{};
};
i64 admission(void* opaque, u64 child_pid, const launch::artifact&, const launch::artifact& wanted, u64 deadline) {
    auto& data = *static_cast<policy*>(opaque);
    if (!child_pid || deadline <= now() || (wanted.id != 1 && wanted.id != 2)) return process_error_denied;
    const auto expected = root(wanted.id);
    if (__builtin_memcmp(&expected, &wanted, sizeof(expected))) return process_error_denied;
    if (wanted.id == 2) {
        ++data.requests;
        if (sdk::equal(data.mode, "prepare-revoke") ||
            (sdk::equal(data.mode, "entry-revoke") && data.requests == 2)) return process_error_denied;
    }
    return 0;
}
i64 prepare_child(u64 pid, void* opaque) {
    auto& data = *static_cast<policy*>(opaque); data.child = pid;
    const u64 budget = sdk::equal(data.mode, "timeout") ? 200'000'000 : 5'000'000'000ULL;
    return launch::record_child(pid, now() + budget, data.control, root(1), admission, &data);
}
u64 start(policy& data) {
    const char* args[]{image, "child", data.mode};
    sdk::spawn_options options{}; options.prepare_child = prepare_child; options.prepare_context = &data;
    const i64 result = sdk::spawn_file_options(image, 3, args, options);
    if (result < 0 && data.child) (void)launch::close_control(data.child);
    require(result > 0 && static_cast<u64>(result) == data.child, "spawn-control-child", result);
    require(!sdk::ipc_send(data.control.ack_handle, &data.control, sizeof(data.control)), "bootstrap-descriptor");
    return data.child;
}
void check_status(u64 pid, const process_status& status, i64 expected) {
    require(status.pid == pid && status.outcome == process_outcome::exited && status.code == expected, "real-wait-result", status.code);
}
int parent(const char* mode) {
    policy first{mode}; const u64 pid = start(first);
    policy second{"success"}; u64 other = 0;
    if (sdk::equal(mode, "multiple")) other = start(second);
    launch::diagnostic diagnostic{};
    const i64 ready = launch::await_ready(pid, diagnostic);
    i64 exit_code = 0;
    if (sdk::equal(mode, "timeout")) {
        require(ready == thread_error_timeout, "initial-timeout", ready); exit_code = 49;
    } else if (sdk::equal(mode, "early-exit")) {
        require(ready < 0, "early-exit-not-ready", ready); exit_code = 50;
    } else if (sdk::equal(mode, "malformed")) {
        require(ready == process_error_invalid, "malformed-not-ready", ready); exit_code = 51;
    } else require(!ready, "await-initial", ready);
    if (sdk::equal(mode, "entry-failure")) exit_code = 47;
    if (sdk::equal(mode, "entry-revoke")) exit_code = 48;
    process_status status{};
    // This public wait must pump successor PREPARE/READY; direct blocking sys20
    // deadlocks these children. The multiple case pumps both registered peers.
    require(!sdk::wait(pid, status), "public-wait"); check_status(pid, status, exit_code);
    require(!launch::last_diagnostic(pid, diagnostic), "diagnostic-retained");
    if (sdk::equal(mode, "entry-failure"))
        require(diagnostic.status == -77 && diagnostic.phase == XOS_LAUNCH_PHASE_INITIALIZE &&
                diagnostic.admitted.id == 2 && diagnostic.generation == 2, "failure-stage-retained");
    if (sdk::equal(mode, "entry-revoke"))
        require(diagnostic.status == process_error_denied && diagnostic.phase == XOS_LAUNCH_PHASE_ENTRY &&
                diagnostic.admitted.id == 2, "entry-stage-retained");
    if (other) { require(!sdk::wait_any(status), "wait-any-second"); check_status(other, status, 0); }
    require(sdk::wait(pid, status) == process_error_denied, "completion-exactly-once");
    channel_info absent{}; require(sdk::channel_get(0, absent) == thread_error_not_found, "channels-reclaimed");
    sdk::print("LAUNCH_PASS "); sdk::print(mode); sdk::print("\n"); return 0;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc == 3 && xos::sdk::equal(args[1], "child")) return child(args[2]);
    if (startup->argc == 4 && xos::sdk::equal(args[1], "after")) return after(startup, args[2], args[3]);
    require(startup->argc == 2, "parent-arguments"); return parent(args[1]);
}
