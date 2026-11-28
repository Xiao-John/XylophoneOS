// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <xos/ipc_v1.hpp>

namespace {
using namespace xos;
constexpr char parent_name[] = "ipc-exec-parent";
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::used, gnu::section(".xos.exec")]] const exec_marker marker{exec_image_abi_magic, 3, 16};
struct packet { u32 stage, reserved; char nonce[32]; u64 value, extra; };
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
void send(const ipc_channel& channel, u32 stage, const char* nonce, u64 payload = 0, u64 extra = 0) {
    packet value{stage, 0, {}, payload, extra}; __builtin_memcpy(value.nonce, nonce, 32);
    const u64 deadline = now() + 5'000'000'000ull;
    for (;;) {
        const i64 result = sdk::ipc_send(channel.send, &value, sizeof(value));
        if (!result) return;
        require(result == ipc_error_full && now() < deadline, "send", result); pause();
    }
}
packet receive(const ipc_channel& channel, u32 stage, const char* nonce) {
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
// Only the worker enters an IPC wait. The observing thread stays runnable,
// and non-supervisor sys50 counts this process alone. Thus waiting == count
// proves actual kernel registration, without timing assumptions or new ABI.
struct waiter { u64 tid; u32 handle; ipc_wait_mode mode; i64 result; };
u64 wait_worker(void* opaque) {
    auto& value = *static_cast<waiter*>(opaque);
    const i64 result = sdk::ipc_wait(value.handle, value.mode);
    __atomic_store_n(&value.result, result, __ATOMIC_RELEASE);
    return 71;
}
void observe_waiters(u32 count) {
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
void start_waiter(waiter& value, u32 handle, ipc_wait_mode mode) {
    value = {0, handle, mode, 12345};
    require(!thread::create(value.tid, wait_worker, &value), "create-waiter");
}
void join_broken(waiter& value) {
    u64 status = 0;
    require(!thread::join(value.tid, status) && status == 71, "join-waiter");
    const i64 result = __atomic_load_n(&value.result, __ATOMIC_ACQUIRE);
    require(result == ipc_error_broken, "blocked-wait-must-return-broken", result);
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

constexpr char service_name[] = "ipc-lifecycle-service";
int lifecycle_service(u64 parent, const char* nonce, const char* event) {
    require(!sdk::ipc_name_publish(service_name), "service-publish");
    ipc_channel empty{};
    require(sdk::ipc_name_try_accept(empty) == process_error_would_block, "restart-has-no-old-connection");
    ipc_channel control{};
    require(!sdk::ipc_name_connect(parent_name, control), "service-control");
    authenticate(control, parent); send(control, 10, nonce);
    ipc_channel data = accept(parent);
    // Receiving an endpoint does not make the service its revocation owner.
    require(sdk::ipc_channel_revoke(data.send) == process_error_denied, "peer-cannot-revoke");
    require(sdk::ipc_wait(data.send, ipc_wait_mode::try_receive) == process_error_denied,
            "endpoint-direction-denied");
    send(control, 11, nonce); receive(control, 12, nonce);
    if (sdk::equal(event, "exit")) return 27;
    if (sdk::equal(event, "fault")) __asm__ volatile("ud2");
    require(!sdk::equal(event, "cancel"), "cancel-child-resumed");
    if (sdk::equal(event, "revoke")) invalidated(data);
    else if (sdk::equal(event, "close")) {
        require(!sdk::ipc_channel_close(data.send), "peer-close"); invalidated(data);
    } else {
        require(sdk::equal(event, "restart"), "service-event");
        receive(data, 20, nonce); send(data, 21, nonce);
    }
    send(control, 13, nonce); receive(control, 14, nonce);
    return 0;
}
struct service_session { u64 pid; ipc_channel control, data; };
service_session launch_service(const char* image, const char* nonce, const char* event) {
    char parent[21]{}; number_text(sdk::pid(), parent);
    const char* args[]{image, "service", parent, nonce, event};
    const i64 pid = sdk::spawn_file(image, 5, args);
    require(pid > 0, "spawn-service", pid);
    service_session value{static_cast<u64>(pid), accept(static_cast<u64>(pid)), {}};
    receive(value.control, 10, nonce);
    require(!sdk::ipc_name_connect(service_name, value.data), "service-connect");
    authenticate(value.data, value.pid); receive(value.control, 11, nonce);
    return value;
}
void wait_service(const service_session& value, process_outcome outcome, i64 code) {
    process_status status{};
    require(!sdk::wait(value.pid, status) && status.pid == value.pid && status.outcome == outcome,
            "service-outcome");
    if (outcome == process_outcome::faulted) require(status.vector == 6, "service-fault-vector");
    else require(status.code == code, "service-exit-code", status.code);
}
void lifecycle_case(const char* image, const char* nonce, const char* event) {
    service_session old = launch_service(image, nonce, event);
    ipc_channel pending{};
    require(!sdk::ipc_name_connect(service_name, pending), "service-pending-connect");
    authenticate(pending, old.pid); send(pending, 99, nonce);
    // Fill one direction and leave the other empty. Both waits must be blocked
    // before the revocation event, so send and receive wakeups are independent.
    send(old.data, 98, nonce);
    waiter receiving{}, sending{};
    start_waiter(receiving, old.data.receive, ipc_wait_mode::receive);
    start_waiter(sending, old.data.send, ipc_wait_mode::send);
    observe_waiters(2);
    sdk::print("IPC_LIFECYCLE_BLOCKED "); sdk::print(event); sdk::print(" receive send\n");
    if (sdk::equal(event, "cancel")) {
        require(!sdk::syscall(sys_process_cancel, old.pid), "cancel-service");
    } else {
        if (sdk::equal(event, "revoke")) require(!sdk::ipc_channel_revoke(old.data.send), "owner-revoke");
        send(old.control, 12, nonce);
    }
    join_broken(receiving); join_broken(sending); invalidated(old.data);
    process_outcome outcome = process_outcome::exited;
    i64 code = 0;
    if (sdk::equal(event, "revoke") || sdk::equal(event, "close")) {
        receive(old.control, 13, nonce);
        process_status alive{};
        require(sdk::syscall(sys_process_wait, old.pid, reinterpret_cast<u64>(&alive), process_wait_nonblocking) ==
                process_error_would_block, "explicit-close-keeps-peer-live");
        authenticate(pending, old.pid); send(old.control, 14, nonce);
    } else if (sdk::equal(event, "fault")) outcome = process_outcome::faulted;
    else if (sdk::equal(event, "cancel")) { outcome = process_outcome::killed; code = -9; }
    else code = 27;
    wait_service(old, outcome, code);
    invalidated(old.control); invalidated(old.data); invalidated(pending);
    ipc_channel absent{};
    require(sdk::ipc_name_connect(service_name, absent) == ipc_error_name_not_found, "dead-service-name-removed");

    // Restart is a userspace decision with a fresh authenticated PID/session.
    // Reusing the name or pool slots must never revive the previous tokens.
    service_session fresh = launch_service(image, nonce, "restart");
    require(fresh.pid != old.pid && fresh.data.send != old.data.send &&
            fresh.data.receive != old.data.receive && fresh.control.send != old.control.send &&
            fresh.control.receive != old.control.receive, "restart-identity-or-token-reuse");
    invalidated(old.control); invalidated(old.data); invalidated(pending);
    send(fresh.control, 12, nonce); send(fresh.data, 20, nonce); receive(fresh.data, 21, nonce);
    receive(fresh.control, 13, nonce); send(fresh.control, 14, nonce);
    wait_service(fresh, process_outcome::exited, 0);
    invalidated(fresh.control); invalidated(fresh.data);
    sdk::print("IPC_LIFECYCLE_PASS "); sdk::print(event); sdk::print(" blocked_both restart_authenticated stale_tokens_denied\n");
}

constexpr u32 call_right = static_cast<u32>(ipc_v1_right::call);
constexpr u32 delegate_right = static_cast<u32>(ipc_v1_right::delegate);
constexpr u32 manage_right = static_cast<u32>(ipc_v1_right::manage);
constexpr u64 delegated_badge = 0x61757468;
i64 ipc_error(ipc_v1_error value) { return static_cast<i64>(value); }
int authority_child(u64 parent, const char* nonce) {
    require(sdk::syscall(sys_process_authority, sdk::pid(),
                        static_cast<u64>(process_authority_mode::query)) == 0, "child-create-right-not-inherited");
    const char name[] = "denied";
    require(sdk::syscall(sys_process_create, 0, reinterpret_cast<u64>(name), sizeof(name) - 1) ==
            process_error_denied, "restricted-child-cannot-create");
    ipc_channel control{}; require(!sdk::ipc_name_connect(parent_name, control), "authority-control");
    authenticate(control, parent); send(control, 30, nonce);
    const packet rights = receive(control, 31, nonce);
    require(ipc_v1::endpoint_close(rights.extra) == ipc_error(ipc_v1_error::invalid_handle), "foreign-handle-denied");
    require(ipc_v1::endpoint_close(rights.value) == ipc_error(ipc_v1_error::denied), "attenuated-manage-denied");
    u64 output = 123;
    require(ipc_v1::endpoint_delegate(rights.value, parent, 0, call_right | manage_right, output) ==
            ipc_error(ipc_v1_error::denied) && output == 0, "delegation-cannot-add-rights");
    ipc_v1_receive forbidden{}; forbidden.handle = rights.value;
    require(ipc_v1::receive(forbidden) == ipc_error(ipc_v1_error::denied), "attenuated-receive-denied");
    require(!ipc_v1::endpoint_delegate(rights.value, parent, 7, call_right, output), "delegation-can-reduce-rights");
    send(control, 32, nonce, output);

    char reply[32]{};
    ipc_v1_call request{}; request.handle = rights.value; request.deadline_ns = now() + 5'000'000'000ull;
    request.label = 41; request.send_buffer = reinterpret_cast<u64>(nonce); request.send_length = 32;
    request.reply_buffer = reinterpret_cast<u64>(reply); request.reply_capacity = sizeof(reply);
    require(!ipc_v1::call(request) && request.reply_length_out == 32 && request.reply_label_out == 42 &&
            request.phase_out == static_cast<u32>(ipc_v1_call_phase::replied) &&
            !__builtin_memcmp(reply, nonce, 32), "delegated-call-reply");

    u64 handles[ipc_v1_max_handles_per_process - 1]{};
    for (auto& handle : handles) require(!ipc_v1::endpoint_create(manage_right, handle), "handle-fill");
    output = 123;
    require(ipc_v1::endpoint_create(manage_right, output) == ipc_error(ipc_v1_error::resources) &&
            output == 0, "handle-quota-atomic-failure");
    const u64 stale = handles[0];
    require(!ipc_v1::endpoint_close(stale) && !ipc_v1::endpoint_create(manage_right, handles[0]) &&
            handles[0] != stale, "handle-quota-recovery");
    require(ipc_v1::endpoint_close(stale) == ipc_error(ipc_v1_error::invalid_handle), "quota-old-token-denied");
    for (auto handle : handles) require(!ipc_v1::endpoint_close(handle), "handle-cleanup");
    send(control, 33, nonce); receive(control, 34, nonce);
    require(ipc_v1::call(request) == ipc_error(ipc_v1_error::invalid_handle) &&
            request.phase_out == static_cast<u32>(ipc_v1_call_phase::not_delivered), "revoked-delegation-denied");
    return 0;
}
void authority_case(const char* image, const char* nonce) {
    char parent[21]{}; number_text(sdk::pid(), parent);
    const char* args[]{image, "authority-child", parent, nonce};
    const i64 pid = sdk::spawn_file(image, 4, args); require(pid > 0, "spawn-authority-child", pid);
    ipc_channel control = accept(static_cast<u64>(pid)); receive(control, 30, nonce);
    u64 owner = 0, child = 0;
    require(!ipc_v1::endpoint_create(ipc_v1_right_all, owner) &&
            !ipc_v1::endpoint_delegate(owner, static_cast<u64>(pid), delegated_badge,
                                      call_right | delegate_right, child), "delegate-child");
    require(ipc_v1::endpoint_close(child) == ipc_error(ipc_v1_error::invalid_handle), "parent-cannot-use-child-handle");
    send(control, 31, nonce, child, owner);
    const packet returned = receive(control, 32, nonce);
    require(ipc_v1::endpoint_close(returned.value) == ipc_error(ipc_v1_error::denied), "redelegated-manage-denied");
    char message[32]{};
    ipc_v1_receive input{}; input.handle = owner; input.deadline_ns = now() + 5'000'000'000ull;
    input.buffer = reinterpret_cast<u64>(message); input.capacity = sizeof(message);
    require(!ipc_v1::receive(input) && input.label_out == 41 && input.badge_out == delegated_badge &&
            input.message_length_out == sizeof(message) && !__builtin_memcmp(message, nonce, 32), "kernel-badge-and-payload");
    ipc_v1_reply reply{}; reply.reply_token = input.reply_token_out; reply.label = 42;
    reply.buffer = reinterpret_cast<u64>(message); reply.length = sizeof(message);
    require(!ipc_v1::reply(reply), "reply-once");
    require(ipc_v1::reply(reply) == ipc_error(ipc_v1_error::stale_token), "reply-cannot-replay");
    receive(control, 33, nonce);
    require(!ipc_v1::endpoint_close(owner), "owner-revokes-delegation");
    require(ipc_v1::endpoint_close(returned.value) == ipc_error(ipc_v1_error::invalid_handle), "revoke-covers-derived-handle");
    send(control, 34, nonce);
    wait_service({static_cast<u64>(pid), control, {}}, process_outcome::exited, 0);
    sdk::print("IPC_AUTHORITY_PASS subject_bound attenuated redelegated revoked reply_once quota_recovered\n");
}

constexpr char quota_peer_name[] = "ipc-quota-peer";
constexpr char quota_peer_second[] = "ipc-quota-peer-second";
constexpr char quota_parent_second[] = "ipc-quota-parent-second";
constexpr char quota_parent_extra[] = "ipc-quota-parent-extra";
void pair_quota_full(u64 peer) {
    ipc_channel unchanged{0x7ffffff0, 0x7ffffff1};
    require(sdk::ipc_channel_create(peer, unchanged) == process_error_resources &&
            unchanged.send == 0x7ffffff0 && unchanged.receive == 0x7ffffff1, "direct-quota-output-unchanged");
    require(sdk::ipc_name_connect(quota_peer_name, unchanged) == process_error_resources &&
            unchanged.send == 0x7ffffff0 && unchanged.receive == 0x7ffffff1, "connect-shares-owner-quota");
}
void name_quota_full() {
    require(sdk::ipc_name_publish(quota_parent_extra) == process_error_resources, "name-quota");
    require(!sdk::ipc_name_publish(parent_name) && !sdk::ipc_name_publish(quota_parent_second),
            "name-publish-idempotent-at-quota");
    require(sdk::ipc_name_unpublish(quota_parent_extra) == process_error_denied, "failed-publish-left-no-name");
}
int quota_peer(u64 parent, const char* nonce) {
    require(!sdk::ipc_name_publish(quota_peer_name) && !sdk::ipc_name_publish(quota_peer_second), "peer-name-budget");
    ipc_channel control{}; require(!sdk::ipc_name_connect(parent_name, control), "quota-control");
    authenticate(control, parent); send(control, 50, nonce);
    const packet direct = receive(control, 51, nonce);
    ipc_channel owner_pair{static_cast<u32>(direct.extra), static_cast<u32>(direct.value)};
    authenticate(owner_pair, parent);
    ipc_channel first = accept(parent), second = accept(parent);
    // Another authenticated owner retains its allocation budget even while
    // the parent has filled both its direct/create and pending/connect quota.
    ipc_channel independent{};
    require(!sdk::ipc_channel_create(parent, independent), "other-owner-can-create");
    authenticate(independent, parent); close(independent);
    require(sdk::ipc_channel_revoke(owner_pair.send) == process_error_denied, "peer-revoke-does-not-release-owner-budget");
    send(control, 52, nonce); receive(control, 53, nonce);
    require(!sdk::ipc_channel_close(owner_pair.send), "peer-close-releases-owner-budget");
    require(sdk::ipc_channel_close(owner_pair.receive) == process_error_denied, "repeat-close-denied");
    send(control, 54, nonce); receive(control, 55, nonce);
    authenticate(first, parent); authenticate(second, parent);
    // Leave both published names and all accepted pair references live. Exit
    // must recover their owners' budgets, including the parent's four pairs.
    return 0;
}
void quota_case(const char* image, const char* nonce) {
    static_assert(ipc_max_owned_channels == 4 && ipc_max_owned_names == 2);
    require(!sdk::ipc_name_publish(quota_parent_second), "second-parent-name"); name_quota_full();
    char parent[21]{}; number_text(sdk::pid(), parent);
    const char* args[]{image, "quota-peer", parent, nonce};
    const i64 pid = sdk::spawn_file(image, 4, args); require(pid > 0, "spawn-quota-peer", pid);
    const u64 peer = static_cast<u64>(pid);
    ipc_channel control = accept(peer); receive(control, 50, nonce);
    require(sdk::ipc_name_publish(quota_peer_name) == process_error_busy, "other-owner-name-conflict");
    ipc_channel channels[ipc_max_owned_channels]{};
    require(!sdk::ipc_channel_create(peer, channels[0]) &&
            !sdk::ipc_name_connect(quota_peer_name, channels[1]) &&
            !sdk::ipc_channel_create(peer, channels[2]) &&
            !sdk::ipc_name_connect(quota_peer_name, channels[3]), "fill-mixed-pair-quota");
    for (const auto& channel : channels) authenticate(channel, peer);
    pair_quota_full(peer); // Pending connections already consume their pairs.
    send(control, 51, nonce, channels[0].send, channels[0].receive);
    receive(control, 52, nonce); pair_quota_full(peer); // Accept is not release.
    waiter blocked{};
    start_waiter(blocked, channels[0].receive, ipc_wait_mode::receive); observe_waiters(1);
    pair_quota_full(peer);
    require(sdk::ipc_channel_revoke(control.send) == process_error_denied &&
            sdk::ipc_channel_close(0x7fffffff) == process_error_denied, "failed-release-denied");
    pair_quota_full(peer); name_quota_full();
    send(control, 53, nonce); join_broken(blocked); receive(control, 54, nonce);
    const ipc_channel stale = channels[0]; invalidated(stale);
    require(!sdk::ipc_channel_create(peer, channels[0]) && channels[0].send != stale.send &&
            channels[0].receive != stale.receive, "peer-close-recovers-one-pair");
    invalidated(stale); pair_quota_full(peer);
    require(sdk::ipc_channel_close(stale.send) == process_error_denied, "stale-release-denied");
    pair_quota_full(peer); // Failed close cannot manufacture another credit.

    require(!sdk::ipc_name_unpublish(quota_parent_second) &&
            !sdk::ipc_name_publish(quota_parent_extra), "name-budget-recovers");
    require(sdk::ipc_name_publish(quota_parent_second) == process_error_resources, "name-budget-still-bounded");
    require(!sdk::ipc_name_unpublish(quota_parent_extra), "parent-extra-unpublish");
    send(control, 55, nonce);
    wait_service({peer, control, {}}, process_outcome::exited, 0);
    for (const auto& channel : channels) invalidated(channel);
    invalidated(control);
    ipc_channel missing{};
    require(sdk::ipc_name_connect(quota_peer_name, missing) == ipc_error_name_not_found &&
            sdk::ipc_name_connect(quota_peer_second, missing) == ipc_error_name_not_found, "peer-exit-reclaims-names");
    // The live supervisor is only a peer for these unused pairs. Neither its
    // identity nor possession of a token grants this process extra authority.
    for (auto& channel : channels) require(!sdk::ipc_channel_create(0, channel), "exit-recovers-full-owner-budget");
    missing = {0x7ffffff0, 0x7ffffff1};
    require(sdk::ipc_channel_create(0, missing) == process_error_resources &&
            missing.send == 0x7ffffff0 && missing.receive == 0x7ffffff1, "recovered-budget-remains-bounded");
    for (auto& channel : channels) {
        require(!sdk::ipc_channel_close(channel.send), "owner-closes-recovered-pair"); invalidated(channel);
    }
    sdk::print("IPC_QUOTA_PASS shared_owner_budget pending_and_accepted_counted blocked_counted failure_atomic peer_isolated recovered\n");
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
    if (sdk::equal(argv[1], "service")) {
        require(startup->argc == 5 && sdk::length(argv[3]) == 32, "service-arguments");
        return lifecycle_service(number(argv[2]), argv[3], argv[4]);
    }
    if (sdk::equal(argv[1], "authority-child")) {
        require(startup->argc == 4 && sdk::length(argv[3]) == 32, "authority-arguments");
        return authority_child(number(argv[2]), argv[3]);
    }
    if (sdk::equal(argv[1], "quota-peer")) {
        require(startup->argc == 4 && sdk::length(argv[3]) == 32, "quota-peer-arguments");
        return quota_peer(number(argv[2]), argv[3]);
    }
    if (sdk::equal(argv[1], "lifecycle") || sdk::equal(argv[1], "authority") || sdk::equal(argv[1], "quota")) {
        require(startup->argc == 3 && sdk::length(argv[2]) == 32, "lifecycle-arguments");
        require(!sdk::ipc_name_publish(parent_name), "publish-parent");
        if (sdk::equal(argv[1], "quota")) quota_case(argv[0], argv[2]);
        else if (sdk::equal(argv[1], "authority")) authority_case(argv[0], argv[2]);
        else {
            const char* events[]{"revoke", "close", "exit", "fault", "cancel"};
            for (const char* event : events) lifecycle_case(argv[0], argv[2], event);
        }
        require(!sdk::ipc_name_unpublish(parent_name), "unpublish-parent");
        return 0;
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
    authenticate(pending, static_cast<u64>(child)); send(pending, 99, nonce);
    waiter blocked{}; start_waiter(blocked, old.receive, ipc_wait_mode::receive); observe_waiters(1);
    sdk::print("IPC_EXEC_BLOCKED receive\n");
    send(old, 4, nonce); join_broken(blocked);
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
