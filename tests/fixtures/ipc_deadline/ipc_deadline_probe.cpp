// SPDX-License-Identifier: Apache-2.0
#include "../ipc_common.hpp"

namespace {
using namespace xos;
using namespace xos::test_ipc;

struct timed_waiter { u64 tid; u32 handle; ipc_wait_mode mode; u64 deadline; i64 result; };
u64 timed_worker(void* opaque) {
    auto& value = *static_cast<timed_waiter*>(opaque);
    const i64 result = sdk::ipc_wait_until(value.handle, value.mode, value.deadline);
    __atomic_store_n(&value.result, result, __ATOMIC_RELEASE);
    return 73;
}
void begin(timed_waiter& value, u32 handle, ipc_wait_mode mode, u64 deadline) {
    value = {0, handle, mode, deadline, 12345};
    require(!thread::create(value.tid, timed_worker, &value), "timed-worker-create");
}
void joined(timed_waiter& value, i64 expected) {
    u64 status = 0;
    require(!thread::join(value.tid, status) && status == 73, "timed-worker-join");
    const i64 actual = __atomic_load_n(&value.result, __ATOMIC_ACQUIRE);
    require(actual == expected, "timed-wait-result", actual);
    if (expected == thread_error_timeout) require(now() >= value.deadline, "no-early-timeout");
}
void pass(const char* message) { sdk::print("IPC_DEADLINE_PASS "); sdk::print(message); sdk::print("\n"); }
void alive(u64 child) {
    process_status status{};
    require(sdk::syscall(sys_process_wait, child, reinterpret_cast<u64>(&status), process_wait_nonblocking) ==
            process_error_would_block, "silent-service-still-alive");
}

int server(u64 parent, const char* nonce) {
    ipc_channel control{}; require(!sdk::ipc_name_connect(parent_name, control), "deadline-control");
    authenticate(control, parent); send(control, 50, nonce);
    const packet input = receive(control, 51, nonce);
    ipc_channel data{static_cast<u32>(input.extra), static_cast<u32>(input.value)};
    authenticate(data, parent); send(control, 52, nonce);
    // This live service intentionally leaves both the empty receive direction
    // and full send direction unchanged until its authenticated controller acts.
    receive(control, 60, nonce); receive(data, 100, nonce); send(data, 101, nonce); send(control, 61, nonce);
    receive(control, 62, nonce); send(data, 102, nonce); send(control, 63, nonce);
    receive(control, 64, nonce); send(data, 103, nonce); send(control, 65, nonce);
    receive(control, 66, nonce);
    require(!sdk::ipc_channel_close(data.send), "timed-peer-close");
    send(control, 67, nonce); receive(control, 68, nonce);
    return 0;
}

int parent(const char* image, const char* nonce) {
    require(!sdk::ipc_name_publish(parent_name), "deadline-parent-publish");
    char parent_text[21]{}; number_text(sdk::pid(), parent_text);
    const char* args[]{image, "child", parent_text, nonce};
    const i64 spawned = sdk::spawn_file(image, 4, args); require(spawned > 0, "deadline-spawn", spawned);
    const u64 child = static_cast<u64>(spawned);
    ipc_channel control = accept(child); receive(control, 50, nonce);
    ipc_channel data{}; require(!sdk::ipc_channel_create(child, data), "deadline-data-create");
    authenticate(data, child); send(control, 51, nonce, data.send, data.receive); receive(control, 52, nonce);

    timed_waiter receive_timeout{};
    begin(receive_timeout, data.receive, ipc_wait_mode::receive, now() + 1'000'000'000ull);
    observe_waiters(1); joined(receive_timeout, thread_error_timeout); alive(child);
    require(sdk::ipc_wait(data.receive, ipc_wait_mode::try_receive) == process_error_would_block,
            "timeout-did-not-invent-message");
    pass("receive_timeout peer_alive");

    send(data, 100, nonce);
    timed_waiter send_timeout{};
    begin(send_timeout, data.send, ipc_wait_mode::send, now() + 1'000'000'000ull);
    observe_waiters(1); joined(send_timeout, thread_error_timeout); alive(child);
    require(sdk::ipc_wait(data.send, ipc_wait_mode::try_send) == process_error_would_block,
            "timeout-did-not-consume-message");
    timed_waiter send_ready{};
    begin(send_ready, data.send, ipc_wait_mode::send, ~u64{0}); observe_waiters(1);
    send(control, 60, nonce); joined(send_ready, 0); receive(control, 61, nonce);
    // Neither successful wait consumes bytes; even an expired deadline observes
    // a ready queue twice. The server validated the original timed-out payload.
    require(!sdk::ipc_wait_until(data.receive, ipc_wait_mode::receive, 0) &&
            !sdk::ipc_wait_until(data.receive, ipc_wait_mode::receive, 1), "readiness-before-expired-deadline");
    receive(data, 101, nonce); pass("send_timeout payload_preserved");
    require(sdk::ipc_wait_until(data.receive, ipc_wait_mode::receive, 0) == thread_error_timeout &&
            sdk::ipc_wait_until(data.receive, ipc_wait_mode::receive, 1) == thread_error_timeout &&
            !sdk::ipc_wait_until(data.send, ipc_wait_mode::send, 0), "immediate-expired-readiness");
    observe_waiters(0); pass("immediate expired readiness_first");

    const u64 deadline = now() + 5'000'000'000ull;
    require(sdk::ipc_wait_until(data.send, ipc_wait_mode::receive, deadline) == process_error_denied &&
            sdk::ipc_wait_until(data.receive, ipc_wait_mode::send, deadline) == process_error_denied,
            "timed-wait-direction");
    u32 file_send = 0, file_receive = 0; require(!sdk::ipc_handles(file_send, file_receive), "file-handles");
    require(sdk::ipc_wait_until(file_receive, ipc_wait_mode::receive, deadline) == process_error_denied &&
            sdk::syscall(sys_ipc_wait, data.receive, static_cast<u64>(ipc_wait_mode::file_reply_until), deadline) ==
            process_error_denied, "generic-and-file-scopes-separate");
    require(sdk::syscall(sys_ipc_wait, data.receive, static_cast<u64>(ipc_wait_mode::receive), deadline) ==
            process_error_invalid && sdk::syscall(sys_ipc_wait, data.receive, 7, 0) == process_error_invalid &&
            sdk::ipc_wait_until(data.receive, ipc_wait_mode::try_receive, deadline) == process_error_invalid,
            "legacy-and-unknown-mode-rejection");
    pass("scope_and_legacy_rejected");

    timed_waiter infinity{}, ready{};
    begin(infinity, data.receive, ipc_wait_mode::receive, ~u64{0}); observe_waiters(1);
    send(control, 62, nonce); joined(infinity, 0); receive(data, 102, nonce); receive(control, 63, nonce);
    begin(ready, data.receive, ipc_wait_mode::receive, now() + 5'000'000'000ull); observe_waiters(1);
    send(control, 64, nonce); joined(ready, 0); receive(data, 103, nonce); receive(control, 65, nonce);
    pass("ready_wakes_receive_send");

    send(data, 104, nonce);
    timed_waiter closed_receive{}, closed_send{};
    begin(closed_receive, data.receive, ipc_wait_mode::receive, ~u64{0} - 1);
    begin(closed_send, data.send, ipc_wait_mode::send, now() + 5'000'000'000ull); observe_waiters(2);
    send(control, 66, nonce); joined(closed_receive, ipc_error_broken); joined(closed_send, ipc_error_broken);
    receive(control, 67, nonce); alive(child); invalidated(data);
    require(__atomic_load_n(&receive_timeout.result, __ATOMIC_ACQUIRE) == thread_error_timeout &&
            __atomic_load_n(&send_timeout.result, __ATOMIC_ACQUIRE) == thread_error_timeout,
            "timeout-completion-is-final");
    require(sdk::ipc_wait_until(data.receive, ipc_wait_mode::receive, 0) == process_error_denied,
            "revoked-token-before-timeout");
    pass("close_wakes_both no_wrap timeout_final");
    send(control, 68, nonce);
    process_status status{};
    require(!sdk::wait(child, status) && status.pid == child && status.outcome == process_outcome::exited &&
            status.code == 0, "deadline-child-exit");
    invalidated(control); require(!sdk::ipc_name_unpublish(parent_name), "deadline-parent-unpublish");
    return 0;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    using namespace xos::test_ipc;
    require(startup && startup->magic == startup_magic && startup->argc >= 3, "deadline-startup");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    if (sdk::equal(args[1], "child")) {
        require(startup->argc == 4 && sdk::length(args[3]) == 32, "deadline-child-arguments");
        return server(number(args[2]), args[3]);
    }
    require(sdk::equal(args[1], "parent") && startup->argc == 3 && sdk::length(args[2]) == 32, "deadline-parent-arguments");
    return parent(args[0], args[2]);
}
