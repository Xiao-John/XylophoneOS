// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>

namespace {
using namespace xos;
constexpr char parent_name[] = "ipc-exec-parent";
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::used, gnu::section(".xos.exec")]] const exec_marker marker{exec_image_abi_magic, 3, 16};
struct packet { u32 stage, reserved; char nonce[32]; };
[[noreturn]] void fail(const char* label, i64 result = 0) {
    sdk::print("IPC_EXEC_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(result); sdk::print("\n"); sdk::exit(91);
}
void require(bool condition, const char* label, i64 result = 0) { if (!condition) fail(label, result); }
u64 now() { const i64 clock = sdk::syscall(sys_clock_monotonic); require(clock >= 0, "clock", clock); return clock; }
void pause() { const i64 result = sdk::syscall(sys_sleep_until, now() + 1'000'000); require(!result, "sleep", result); }
void number_text(u64 value, char* text) {
    char reverse[21]; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
    u32 index = 0; while (count) text[index++] = reverse[--count]; text[index] = 0;
}
u64 number(const char* text) {
    require(text && *text, "number-empty"); u64 value = 0;
    while (*text) {
        require(*text >= '0' && *text <= '9' && value <= (~u64{0} - 9) / 10, "number-invalid");
        value = value * 10 + static_cast<u64>(*text++ - '0');
    }
    return value;
}
void child_name(u64 pid, char (&text)[32]) {
    constexpr char prefix[] = "ipc-exec-";
    __builtin_memcpy(text, prefix, sizeof(prefix) - 1); number_text(pid, text + sizeof(prefix) - 1);
}
void close(ipc_channel& channel) {
    if (channel.send) (void)sdk::ipc_channel_close(channel.send);
    if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
    channel = {};
}
void authenticate(const ipc_channel& channel, u64 peer) {
    u64 send_peer = 0, receive_peer = 0;
    require(!sdk::ipc_endpoint_peer(channel.send, send_peer) && !sdk::ipc_endpoint_peer(channel.receive, receive_peer) &&
            send_peer == peer && receive_peer == peer, "authenticate");
}
void send(const ipc_channel& channel, u32 stage, const char* nonce) {
    packet value{stage, 0, {}}; __builtin_memcpy(value.nonce, nonce, 32);
    const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_send(channel.send, &value, sizeof(value));
        if (!result) return;
        require(result == ipc_error_full && now() < deadline, "send", result); pause();
    }
}
void receive(const ipc_channel& channel, u32 stage, const char* nonce) {
    packet value{}; const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_recv(channel.receive, &value, sizeof(value));
        if (result != -3) {
            require(result == sizeof(value) && value.stage == stage && !value.reserved &&
                    !__builtin_memcmp(value.nonce, nonce, 32), "receive-identity-or-bytes", result); return;
        }
        require(now() < deadline, "receive-timeout"); pause();
    }
}
ipc_channel accept(u64 peer) {
    ipc_channel channel{}; const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_name_try_accept(channel);
        if (!result) { authenticate(channel, peer); return channel; }
        require(result == process_error_would_block && now() < deadline, "accept", result); pause();
    }
}
void invalidated(const ipc_channel& channel) {
    packet value{}; u64 peer = 0;
    require(sdk::ipc_send(channel.send, &value, sizeof(value)) < 0, "old-send-live");
    require(sdk::ipc_recv(channel.receive, &value, sizeof(value)) < 0, "old-receive-live");
    require(sdk::ipc_endpoint_peer(channel.send, peer) == process_error_denied &&
            sdk::ipc_endpoint_peer(channel.receive, peer) == process_error_denied, "old-auth-live");
}
int before(const char* image, u64 parent, const char* nonce) {
    char name[32]{}, parent_text[21]{}, send_text[21]{}, receive_text[21]{};
    child_name(sdk::pid(), name); number_text(parent, parent_text);
    require(!sdk::ipc_name_publish(name), "publish-before");
    ipc_channel old{};
    require(!sdk::ipc_name_connect(parent_name, old), "connect-before"); authenticate(old, parent);
    number_text(old.send, send_text); number_text(old.receive, receive_text);
    const char* arguments[]{image, "after", parent_text, nonce, send_text, receive_text};
    // The replacement maps successfully, then the kernel rejects its invalid
    // authority depth. The queued message and published name must survive.
    send(old, 1, nonce);
    sdk::spawn_options options{}; options.replace_image = true; options.exec_depth_mode = 0xffffffffu;
    const i64 rejected = sdk::spawn_file_options(image, 6, arguments, options);
    require(rejected == process_error_delegation, "failed-commit-error", rejected);
    authenticate(old, parent); receive(old, 2, nonce);
    // The parent connects the original name below, without republishing it.
    send(old, 3, nonce); receive(old, 4, nonce);
    options.exec_depth_mode = 0;
    fail("successful-exec-returned", sdk::spawn_file_options(image, 6, arguments, options));
}
int after(const startup_info* startup, u64 parent, const char* nonce, u32 old_send, u32 old_receive) {
    require(startup->version == 3 && startup->reserved == startup_extension_offset, "exec-startup-version");
    const auto* snapshot = reinterpret_cast<const startup_exec_extension*>(reinterpret_cast<const u8*>(startup) + startup_exec_offset);
    require(snapshot->magic == startup_exec_magic && !snapshot->count && !snapshot->reserved, "exec-empty-snapshot");
    ipc_channel old{old_send, old_receive}; invalidated(old);
    char name[32]{}; child_name(sdk::pid(), name);
    require(sdk::ipc_name_unpublish(name) == process_error_denied, "exec-old-name-still-owned");
    require(!sdk::ipc_name_publish(name), "exec-old-name-removed");
    ipc_channel pending{};
    require(sdk::ipc_name_try_accept(pending) == process_error_would_block, "exec-pending-connection-destroyed");
    ipc_channel fresh{}; require(!sdk::ipc_name_connect(parent_name, fresh), "connect-after"); authenticate(fresh, parent);
    require(fresh.send != old.send && fresh.receive != old.receive, "opaque-token-reuse");
    send(fresh, 5, nonce); receive(fresh, 6, nonce);
    close(fresh); require(!sdk::ipc_name_unpublish(name), "unpublish-after");
    sdk::print("IPC_EXEC_CHILD_PASS\n"); return 0;
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    require(startup && startup->magic == startup_magic && startup->argc >= 3, "startup");
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    if (sdk::equal(argv[1], "before")) {
        require(startup->argc == 4 && sdk::length(argv[3]) == 32, "before-arguments");
        return before(argv[0], number(argv[2]), argv[3]);
    }
    if (sdk::equal(argv[1], "after")) {
        require(startup->argc == 6 && sdk::length(argv[3]) == 32, "after-arguments");
        return after(startup, number(argv[2]), argv[3], static_cast<u32>(number(argv[4])), static_cast<u32>(number(argv[5])));
    }
    require(sdk::equal(argv[1], "parent") && startup->argc == 3 && sdk::length(argv[2]) == 32, "parent-arguments");
    const char* nonce = argv[2]; require(!sdk::ipc_name_publish(parent_name), "publish-parent");
    char parent_text[21]{}; number_text(sdk::pid(), parent_text);
    const char* arguments[]{argv[0], "before", parent_text, nonce};
    sdk::spawn_options options{};
    const i64 child = sdk::spawn_file_options(argv[0], 4, arguments, options);
    require(child > 0, "spawn-child", child);
    ipc_channel old = accept(static_cast<u64>(child)); receive(old, 1, nonce); send(old, 2, nonce);
    receive(old, 3, nonce);
    // Keep an unaccepted connection with a queued private message across exec.
    char name[32]{}; child_name(static_cast<u64>(child), name);
    ipc_channel pending{}; require(!sdk::ipc_name_connect(name, pending), "failed-commit-name-connect");
    authenticate(pending, static_cast<u64>(child)); send(pending, 99, nonce); send(old, 4, nonce);
    const i64 wake = sdk::ipc_wait(old.receive, ipc_wait_mode::receive);
    require(wake == ipc_error_broken || wake == process_error_denied, "exec-wakes-peer", wake);
    invalidated(old); invalidated(pending);
    ipc_channel fresh = accept(static_cast<u64>(child)); receive(fresh, 5, nonce); send(fresh, 6, nonce);
    process_status status{}; const i64 waited = sdk::wait(static_cast<u64>(child), status);
    require(!waited && status.outcome == process_outcome::exited && status.code == 0, "child-exit", waited);
    close(fresh); close(old); close(pending);
    require(sdk::ipc_name_connect(name, pending) == ipc_error_name_not_found, "child-name-after-exit");
    require(!sdk::ipc_name_unpublish(parent_name), "unpublish-parent");
    sdk::print("IPC_EXEC_PASS failed_commit_preserved success_revoked pending_destroyed same_pid_reconnected\n");
    return 0;
}
