// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <xos/ipc_v1.hpp>

namespace xos::test_ipc {
using namespace xos;
constexpr char parent_name[] = "ipc-exec-parent";
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::used, gnu::section(".xos.exec")]] const exec_marker marker{exec_image_abi_magic, 3, 16};
struct packet { u32 stage, reserved; char nonce[32]; u64 value, extra; };
[[noreturn]] inline void fail(const char* label, i64 result = 0) {
    sdk::print("IPC_EXEC_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(result); sdk::print("\n"); sdk::exit(91);
}
inline void require(bool condition, const char* label, i64 result = 0) { if (!condition) fail(label, result); }
inline u64 now() { const i64 clock = sdk::syscall(sys_clock_monotonic); require(clock >= 0, "clock", clock); return clock; }
inline void pause() { const i64 result = sdk::syscall(sys_sleep_until, now() + 1'000'000); require(!result, "sleep", result); }
inline void number_text(u64 value, char* text) {
    char reverse[21]; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
    u32 index = 0; while (count) text[index++] = reverse[--count]; text[index] = 0;
}
inline u64 number(const char* text) {
    require(text && *text, "number-empty"); u64 value = 0;
    while (*text) {
        require(*text >= '0' && *text <= '9' && value <= (~u64{0} - 9) / 10, "number-invalid");
        value = value * 10 + static_cast<u64>(*text++ - '0');
    }
    return value;
}
inline void child_name(u64 pid, char (&text)[32]) {
    constexpr char prefix[] = "ipc-exec-";
    __builtin_memcpy(text, prefix, sizeof(prefix) - 1); number_text(pid, text + sizeof(prefix) - 1);
}
inline void close(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
inline void authenticate(const ipc_channel& channel, u64 peer) {
    u64 send_peer = 0, receive_peer = 0;
    require(!sdk::ipc_endpoint_peer(channel.send, send_peer) && !sdk::ipc_endpoint_peer(channel.receive, receive_peer) &&
            send_peer == peer && receive_peer == peer, "authenticate");
}
inline void send(const ipc_channel& channel, u32 stage, const char* nonce, u64 payload = 0, u64 extra = 0) {
    packet value{stage, 0, {}, payload, extra}; __builtin_memcpy(value.nonce, nonce, 32);
    const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_send(channel.send, &value, sizeof(value));
        if (!result) return;
        require(result == ipc_error_full && now() < deadline, "send", result); pause();
    }
}
inline packet receive(const ipc_channel& channel, u32 stage, const char* nonce) {
    packet value{}; const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_recv(channel.receive, &value, sizeof(value));
        if (result != -3) {
            require(result == sizeof(value) && value.stage == stage && !value.reserved &&
                    !__builtin_memcmp(value.nonce, nonce, 32), "receive-identity-or-bytes", result); return value;
        }
        require(now() < deadline, "receive-timeout"); pause();
    }
}
inline ipc_channel accept(u64 peer) {
    ipc_channel channel{}; const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_name_try_accept(channel);
        if (!result) { authenticate(channel, peer); return channel; }
        require(result == process_error_would_block && now() < deadline, "accept", result); pause();
    }
}
inline void invalidated(const ipc_channel& channel) {
    packet value{}; u64 peer = 0;
    require(sdk::ipc_send(channel.send, &value, sizeof(value)) < 0, "old-send-live");
    require(sdk::ipc_recv(channel.receive, &value, sizeof(value)) < 0, "old-receive-live");
    require(sdk::ipc_endpoint_peer(channel.send, peer) == process_error_denied &&
            sdk::ipc_endpoint_peer(channel.receive, peer) == process_error_denied, "old-auth-live");
}
// Only the worker enters an IPC wait. The observing thread stays runnable,
// and non-supervisor sys50 counts this process alone. Thus waiting == count
// proves actual kernel registration, without timing assumptions or new ABI.
struct waiter { u64 tid; u32 handle; ipc_wait_mode mode; i64 result; };
inline u64 wait_worker(void* opaque) {
    auto& value = *static_cast<waiter*>(opaque);
    const i64 result = sdk::ipc_wait(value.handle, value.mode);
    __atomic_store_n(&value.result, result, __ATOMIC_RELEASE);
    return 71;
}
inline void observe_waiters(u32 count) {
    const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        thread_stats state{};
        require(!sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&state)), "wait-stats");
        require(state.threads == count + 1 && !state.reserved && !state.results, "wait-thread-isolation");
        if (state.waiting == count) return;
        require(now() < deadline, "wait-registration-timeout");
        sdk::yield();
    }
}
inline void start_waiter(waiter& value, u32 handle, ipc_wait_mode mode) {
    value = {0, handle, mode, 12345};
    require(!thread::create(value.tid, wait_worker, &value), "create-waiter");
}
inline void join_broken(waiter& value) {
    u64 status = 0;
    require(!thread::join(value.tid, status) && status == 71, "join-waiter");
    const i64 result = __atomic_load_n(&value.result, __ATOMIC_ACQUIRE);
    require(result == ipc_error_broken, "blocked-wait-must-return-broken", result);
}
}
