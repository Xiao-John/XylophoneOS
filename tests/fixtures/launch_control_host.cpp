// SPDX-License-Identifier: Apache-2.0
// Production controller; only the kernel trap boundary is modeled here.
#include <xos/launch_control.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <sys/wait.h>
#include <unistd.h>

namespace model {
using namespace xos;
constexpr u64 parent = 100, first_child = 200;
u64 self = parent, clock_value = 1'000'000, entropy = 1234;
u32 entropy_calls = 0, create_calls = 0, fail_create = 0, waits = 0;
bool zero_entropy = false;
struct endpoint { u32 handle; u64 sender, receiver, owner; bool open, full; u64 length; u8 bytes[128]; };
endpoint endpoints[32]{};
struct completion { u64 pid; i64 code; bool done, consumed; };
completion completions[8]{};
std::function<void()> event;
void require(bool value, const char* message) {
    if (!value) { std::fprintf(stderr, "FAIL %s\n", message); std::abort(); }
}
endpoint* get(u32 handle) {
    for (auto& item : endpoints) if (item.open && item.handle == handle) return &item;
    return nullptr;
}
u32 open_count() { u32 n = 0; for (const auto& item : endpoints) if (item.open) ++n; return n; }
template<class F> auto child(u64 pid, F operation) {
    const u64 old = self; self = pid; const auto result = operation(); self = old; return result;
}
void finish(u64 pid, i64 code) {
    for (auto& item : completions) if (!item.pid || item.pid == pid) { item = {pid, code, true, false}; break; }
    for (auto& item : endpoints) if (item.sender == pid || item.receiver == pid) item.open = false;
}
launch::artifact root(u64 id) { launch::artifact value{}; value.id = id; value.sha256[0] = static_cast<u8>(id); return value; }
struct policy { bool denied = false, expire = false, fork_lock = false; u32 calls = 0; };
i64 admit(void* opaque, u64, const launch::artifact&, const launch::artifact&, u64 deadline) {
    auto& value = *static_cast<policy*>(opaque); ++value.calls;
    if (value.expire) clock_value = deadline;
    if (value.fork_lock) {
        value.fork_lock = false;
        const pid_t pid = ::fork(); require(pid >= 0, "host fork");
        if (!pid) { self = 300; ::_exit(launch::poll() == 0 && open_count() == 0 ? 0 : 1); }
        int status = 0; require(::waitpid(pid, &status, 0) == pid && WIFEXITED(status) && !WEXITSTATUS(status), "copied lock reset");
    }
    return value.denied ? process_error_denied : 0;
}
launch::descriptor record(u64 pid = first_child, policy* value = nullptr) {
    launch::descriptor control{};
    require(!launch::record_child(pid, clock_value + 1'000'000'000, control,
        value ? root(1) : launch::artifact{}, value ? admit : nullptr, value), "record");
    require(open_count() <= 4, "owner quota preserved"); return control;
}
void ready(const launch::descriptor& value, policy* rule = nullptr) {
    require(!child(value.child_pid, [&] { return launch::notify_ready(value, rule ? root(1) : launch::artifact{}); }), "initial READY/ACK");
}
launch::message packet(const launch::descriptor& value, u32 type, const launch::artifact& artifact = {}, u64 deadline = 0) {
    return {XOS_LAUNCH_CONTROL_MAGIC, 1, sizeof(launch::message), type, 0, value.generation,
            value.nonce, value.child_pid, deadline ? deadline : value.deadline, 0, artifact, {0, 0, 0}};
}
void send(const launch::descriptor& value, const launch::message& message) {
    require(!child(value.child_pid, [&] { return sdk::ipc_send(value.ready_handle, &message, sizeof(message)); }), "raw send");
}
launch::message receive(const launch::descriptor& value) {
    launch::message message{};
    require(child(value.child_pid, [&] { return sdk::ipc_recv(value.ack_handle, &message, sizeof(message)); }) == sizeof(message), "raw receive");
    return message;
}
}

namespace xos::sdk {
i64 syscall(u64 number, u64 a, u64 b, u64 c) {
    using namespace model;
    if (number == 6) return static_cast<i64>(self);
    if (number == sys_clock_monotonic) return static_cast<i64>(clock_value);
    if (number == sys_random_bytes) { ++entropy_calls; *reinterpret_cast<u64*>(a) = zero_entropy ? 0 : ++entropy; return 0; }
    if (number == 4 || number == 5) {
        auto* item = get(static_cast<u32>(a));
        if (!item) return ipc_error_broken;
        if ((number == 4 ? item->sender : item->receiver) != self) return process_error_denied;
        if (number == 4) {
            if (item->full) return -4;
            if (c > sizeof(item->bytes)) return process_error_invalid;
            std::memcpy(item->bytes, reinterpret_cast<void*>(b), c); item->length = c; item->full = true; return 0;
        }
        if (!item->full) return -3;
        if (c < item->length) return process_error_invalid;
        std::memcpy(reinterpret_cast<void*>(b), item->bytes, item->length); item->full = false;
        return static_cast<i64>(item->length);
    }
    if (number == sys_process_wait) {
        for (auto& item : completions) if (item.pid && ((c & process_wait_any) || item.pid == a)) {
            if (item.consumed) continue;
            if (item.done) { *reinterpret_cast<process_status*>(b) = {1, process_outcome::exited, item.pid, item.code, 0, 0, 0}; item.consumed = true; return 0; }
        }
        for (const auto& item : completions) if (item.pid == a && item.consumed) return process_error_denied;
        return process_error_would_block;
    }
    if (number == sys_sleep_until) { ++waits; if (event) event(); else clock_value = a; return 0; }
    if (number != sys_channel) { require(false, "unexpected syscall"); return -999; }
    const auto action = static_cast<channel_action>(a);
    if (action == channel_action::create) {
        ++create_calls;
        if (create_calls == fail_create || open_count() == 4) return process_error_resources;
        const auto& request = *reinterpret_cast<const channel_create*>(b);
        require(request.capacity == 128 && request.version == 1, "channel shape");
        for (u32 i = 0; i < 32; ++i) if (!endpoints[i].open) {
            endpoints[i] = {i + 1, request.sender_pid, request.receiver_pid, self, true, false, 0, {}};
            return static_cast<i64>(i + 1);
        }
        return process_error_resources;
    }
    if (action == channel_action::enumerate) {
        u32 index = 0;
        for (const auto& item : endpoints) if (item.open && (item.sender == self || item.receiver == self)) {
            if (index++ != b) continue;
            *reinterpret_cast<channel_info*>(c) = {1, sizeof(channel_info), item.handle,
                self == item.sender ? channel_send : channel_receive,
                self == item.sender ? item.receiver : item.sender, item.owner}; return 0;
        }
        return thread_error_not_found;
    }
    if (action == channel_action::close) {
        auto* item = get(static_cast<u32>(b)); if (!item) return thread_error_not_found;
        require(item->owner == self || item->sender == self || item->receiver == self, "close ownership"); item->open = false; return 0;
    }
    if (action == channel_action::wait || action == channel_action::wait_many) {
        ++waits;
        if (self != parent) {
            const u64 previous = self; self = parent; require(!launch::poll(), "controller pump"); self = previous;
        } else if (event) event();
        const auto available = [&](u32 handle) {
            const auto* item = get(handle);
            return item && (item->sender == self ? !item->full : item->full);
        };
        if (action == channel_action::wait) {
            if (available(static_cast<u32>(b))) return 0;
            if (!get(static_cast<u32>(b))) return thread_error_not_found;
        } else {
            const auto& request = *reinterpret_cast<const channel_wait_many_request*>(b);
            for (u32 i = 0; i < request.count; ++i) if (available(request.handles[i])) return 0;
        }
        clock_value = c; return thread_error_timeout;
    }
    require(false, "unexpected channel action"); return -999;
}
}

int main(int argc, char** argv) {
    using namespace model;
    require(argc == 2, "case argument"); const char* name = argv[1];
    if (!std::strcmp(name, "registration")) {
        launch::descriptor output{}; output.magic = 777;
        const u64 invalid_deadlines[]{0, ~u64{0}, clock_value, clock_value + XOS_LAUNCH_CONTROL_MAX_NS + 1};
        for (const u64 deadline : invalid_deadlines)
            require(launch::record_child(first_child, deadline, output) < 0 && output.magic == 777 && !open_count(), "invalid deadline atomic");
        require(launch::record_child(first_child, clock_value + 100, output, root(1)) == process_error_denied, "identity not authority");
        zero_entropy = true;
        require(launch::record_child(first_child, clock_value + 100, output) == random_error_io && entropy_calls == 4, "entropy finite retries");
        zero_entropy = false; fail_create = 2;
        require(launch::record_child(first_child, clock_value + 100, output) == process_error_resources && !open_count() && output.magic == 777, "partial channel rollback");
        fail_create = 0; (void)record(); (void)record(201);
        require(launch::record_child(202, clock_value + 100, output) == process_error_resources && open_count() == 4, "per owner quota four");
    } else if (!std::strcmp(name, "fork_lock")) {
        policy rule{}; rule.fork_lock = true; (void)record(first_child, &rule);
        require(open_count() == 2 && !launch::poll(), "parent lock unchanged by fork");
    } else if (!std::strcmp(name, "authentication")) {
        const auto original = record(); auto wrong = original; wrong.child_pid = 201;
        require(child(first_child, [&] { return launch::notify_ready(wrong); }) == process_error_denied, "wrong PID denied");
        wrong = original; wrong.controller_pid = 999;
        require(child(first_child, [&] { return launch::notify_ready(wrong); }) == process_error_denied, "wrong controller denied");
        wrong = original; wrong.ready_handle = original.ack_handle; wrong.ack_handle = original.ready_handle;
        require(child(first_child, [&] { return launch::notify_ready(wrong); }) == process_error_denied, "wrong direction denied");
        wrong = original; wrong.reserved[0] = 1;
        require(child(first_child, [&] { return launch::notify_ready(wrong); }) == process_error_invalid, "reserved descriptor denied"); ready(original);
    } else if (!std::strncmp(name, "malformed_", 10)) {
        const auto control = record(); auto request = packet(control, XOS_LAUNCH_READY);
        if (!std::strcmp(name + 10, "reserved")) request.reserved[0] = 1;
        else if (!std::strcmp(name + 10, "nonce")) ++request.nonce;
        else if (!std::strcmp(name + 10, "pid")) ++request.pid;
        else require(false, "malformed case");
        send(control, request); require(!launch::poll() && !open_count(), "malformed closes authority");
        launch::diagnostic d{}; require(!launch::last_diagnostic(control.child_pid, d) && d.status == process_error_invalid, "malformed diagnostic");
    } else if (!std::strcmp(name, "initial_timeout")) {
        const auto control = record(); clock_value = control.deadline;
        launch::diagnostic d{};
        require(launch::await_ready(control.child_pid, d) == thread_error_timeout && !open_count(), "initial finite timeout");
    } else if (!std::strcmp(name, "callback_timeout")) {
        policy rule{}; const auto control = record(first_child, &rule); ready(control, &rule); rule.expire = true;
        launch::descriptor pending{}; pending.magic = 777;
        require(child(first_child, [&] { return launch::prepare_exec(control, clock_value + 100, root(2), pending); }) == thread_error_timeout && pending.magic == 777, "callback cannot extend deadline");
    } else if (!std::strcmp(name, "revocation")) {
        policy rule{}; const auto control = record(first_child, &rule); ready(control, &rule);
        launch::descriptor next{}; rule.denied = true;
        require(child(first_child, [&] { return launch::prepare_exec(control, clock_value + 1000, root(2), next); }) == process_error_denied, "PREPARE current admission");
        rule.denied = false;
        require(!child(first_child, [&] { return launch::prepare_exec(control, clock_value + 1000, root(2), next); }), "prepare allowed"); rule.denied = true;
        require(!child(first_child, [&] { return launch::cancel_exec(next, root(2)); }), "revocation permits cancel cleanup");
        rule.denied = false;
        require(!child(first_child, [&] { return launch::prepare_exec(control, clock_value + 1000, root(2), next); }), "new candidate"); rule.denied = true;
        require(child(first_child, [&] { return launch::notify_ready(next, root(2)); }) == process_error_denied, "READY current admission");
        launch::diagnostic d{}; require(!launch::last_diagnostic(first_child, d) && d.phase == XOS_LAUNCH_PHASE_ENTRY && d.admitted.id == 2, "ENTRY denial root");
    } else if (!std::strcmp(name, "failure")) {
        const auto control = record(); ready(control); launch::descriptor next{};
        require(!child(first_child, [&] { return launch::prepare_exec(control, clock_value + 1000, next); }), "prepare");
        require(!child(first_child, [&] { return launch::notify_ready(next, -77, XOS_LAUNCH_PHASE_INITIALIZE); }), "failure ACK");
        finish(first_child, 47); process_status status{};
        require(!sdk::wait(first_child, status) && status.code == 47, "actual completion");
        launch::diagnostic d{}; require(!launch::last_diagnostic(first_child, d) && d.status == -77 && d.phase == XOS_LAUNCH_PHASE_INITIALIZE, "failure retained after close");
        require(sdk::wait(first_child, status) == process_error_denied && !open_count(), "completion exactly once");
    } else if (!std::strcmp(name, "stale_allow") || !std::strcmp(name, "stale_cancel")) {
        const auto control = record(); ready(control); launch::descriptor next{};
        const u64 deadline = clock_value + 1000;
        if (!std::strcmp(name, "stale_allow")) {
            send(control, packet(control, XOS_LAUNCH_PREPARE, {}, deadline)); require(!launch::poll(), "queued ALLOW");
        } else {
            require(!child(first_child, [&] { return launch::prepare_exec(control, deadline, next); }), "first prepare");
            send(next, packet(next, XOS_LAUNCH_CANCEL)); require(!launch::poll(), "queued CANCEL_ACK");
        }
        clock_value = deadline + 1;
        require(!child(first_child, [&] { return launch::prepare_exec(control, clock_value + 1000, next); }) && next.generation == 3, "expired reply drained without replay");
        require(!child(first_child, [&] { return launch::notify_ready(next); }), "new generation READY");
    } else if (!std::strcmp(name, "backpressure")) {
        const auto control = record(); const auto filler = packet(control, XOS_LAUNCH_READY_ACK);
        require(!sdk::ipc_send(control.ack_handle, &filler, sizeof(filler)), "fill ACK slot");
        send(control, packet(control, XOS_LAUNCH_READY)); require(!launch::poll(), "queued READY_ACK");
        clock_value = control.deadline; launch::diagnostic d{};
        require(launch::await_ready(first_child, d) == thread_error_timeout && !open_count(), "queued ACK cannot extend authority");
    } else if (!std::strcmp(name, "wait_pump")) {
        const auto first = record(), second = record(201); ready(first); ready(second);
        process_status status{}; const u32 before = waits;
        require(sdk::wait_flags(first_child, status, process_wait_nonblocking) == process_error_would_block && waits == before, "WNOHANG never sleeps");
        int step = 0; launch::descriptor one{}, two{};
        event = [&] {
            if (!step++) {
                require(!child(first_child, [&] { return launch::prepare_exec(first, clock_value + 1000, one); }), "wait child one PREPARE");
                require(!child(201, [&] { return launch::prepare_exec(second, clock_value + 1000, two); }), "wait child two PREPARE");
                require(!child(first_child, [&] { return launch::notify_ready(one); }), "wait child one READY");
                require(!child(201, [&] { return launch::notify_ready(two); }), "wait child two READY");
                finish(first_child, 11); finish(201, 12);
            }
        };
        require(!sdk::wait(first_child, status) && status.code == 11, "blocking public wait pumps peers");
        require(!sdk::wait_any(status) && status.pid == 201 && status.code == 12 && !open_count(), "wait any completion");
    } else if (!std::strcmp(name, "early_completion")) {
        const auto control = record(); finish(first_child, 50); launch::diagnostic d{};
        require(launch::await_ready(control.child_pid, d) < 0, "exit is not READY"); process_status status{};
        require(!sdk::wait(first_child, status) && status.code == 50, "early completion cached");
        require(sdk::wait(first_child, status) == process_error_denied, "cached completion once");
    } else require(false, "unknown case");
    std::printf("PASS launch-control host %s\n", name);
}
