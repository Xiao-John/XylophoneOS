// SPDX-License-Identifier: Apache-2.0
#include <xos/ipc_v1.hpp>
#include <xos/thread_core.hpp>
#include <xos/vm_abi.hpp>

namespace {
using namespace xos;
constexpr u64 arena = 0x100060000000ull, page_bytes = 4096;
constexpr u64 marker = 0x584f5352454c5331ull, second = 1'000'000'000ull;
constexpr char name[] = "p1_grant_release";
constexpr char binary[] = "/bin/grant_release.elf";
constexpr i64 invalid_handle = static_cast<i64>(ipc_v1_error::invalid_handle);
void require(bool okay, const char* label, i64 result = 0) {
    if (okay) return;
    sdk::print("GRANT_RELEASE_FAIL "); sdk::print(label); sdk::print(" result=");
    sdk::signed_decimal(result); sdk::print("\n"); sdk::exit(92);
}
u64 now() { const i64 value = sdk::syscall(sys_clock_monotonic); require(value >= 0, "clock"); return value; }
void pause() { require(!sdk::syscall(sys_sleep_until, now() + 1'000'000ull), "pause"); }
void decimal(u64 value, char* text) {
    char reverse[24]{}; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
    for (u32 i = 0; i < count; ++i) text[i] = reverse[count - i - 1];
    text[count] = 0;
}
u64 number(const char* text) { u64 result = 0; while (*text) { require(*text >= '0' && *text <= '9', "number"); result = result * 10 + *text++ - '0'; } return result; }
u64 create(u32 rights = 11) {
    u64 source[512]{}; source[0] = marker;
    u64 handle = 0, length = 0;
    require(!ipc_v1::grant_create(reinterpret_cast<u64>(source), sizeof(source), rights, handle, length) &&
            handle && length == page_bytes, "create"); return handle;
}
u64 map(u64 handle, u64 address, ipc_v1_grant_access access = ipc_v1_grant_access::read_write) {
    u64 id = 0, length = 0;
    const auto result = ipc_v1::grant_map(handle, address, access, id, length);
    require(!result && id && length == page_bytes, "map", result); return id;
}
void readable(u64 address) { require(*reinterpret_cast<volatile u64*>(address) == marker, "mapping-retained"); }
void released(u64 handle) {
    u64 id = 0, length = 0;
    require(ipc_v1::grant_map(handle, arena + 0x800000, ipc_v1_grant_access::read, id, length) == invalid_handle &&
            ipc_v1::grant_release(handle) == invalid_handle, "stale-handle");
}
i64 vm(vm_operation action, u64 address) {
    vm_request request{vm_abi_version, sizeof(vm_request), static_cast<u32>(action),
        action == vm_operation::reserve ? vm_exact_nonreplace : 0, address, page_bytes,
        action == vm_operation::reserve ? page_bytes : 0, 0, 0, 0, 0};
    return sdk::syscall(sys_vm, reinterpret_cast<u64>(&request));
}
void send(ipc_channel channel, u64 value) { require(!sdk::ipc_send(channel.send, &value, sizeof(value)), "send"); }
u64 receive(ipc_channel channel) {
    const auto result = sdk::ipc_wait_until(channel.receive, ipc_wait_mode::receive, now() + 10 * second);
    require(!result, "channel-wait", result);
    u64 value = 0; require(sdk::ipc_recv(channel.receive, &value, sizeof(value)) == sizeof(value), "receive"); return value;
}
process_budget_snapshot budget() {
    process_budget_snapshot result{};
    require(!sdk::query_process_budget(sdk::pid(), result), "budget-query"); return result;
}
void features() {
    for (u32 flags = 0; flags < 4; ++flags) {
        ipc_v1_feature_query query{};
        require(!ipc_v1::query_features(query, flags & 1, flags & 2) &&
                query.known_features == (flags & 2 ? 0x3f : 0x1f) &&
                query.supported_features == query.known_features, "feature-opt-in");
    }
    const auto handle = create(); map(handle, arena);
    ipc_v1_object_close request{{1, sizeof(request), 0}, handle, {1, 0}};
    require(sdk::syscall(sys_ipc_v1, 24, reinterpret_cast<u64>(&request)) ==
            static_cast<i64>(ipc_v1_error::invalid_argument), "malformed-release");
    request.reserved[0] = 0; request.header.version = 2;
    require(sdk::syscall(sys_ipc_v1, 24, reinterpret_cast<u64>(&request)) ==
            static_cast<i64>(ipc_v1_error::unsupported), "release-version");
    request.header.version = 1;
    require(sdk::syscall(sys_ipc_v1, 24, reinterpret_cast<u64>(&request), 1) ==
            static_cast<i64>(ipc_v1_error::invalid_argument), "release-flags");
    readable(arena);
    require(ipc_v1::grant_close(handle) == static_cast<i64>(ipc_v1_error::denied), "no-manage-revoke");
    require(!ipc_v1::grant_release(handle), "release-after-invalid"); released(handle);
}
void quota() {
    u64 handles[ipc_v1_max_handles_per_process]{};
    for (auto& handle : handles) handle = create(1);
    u64 denied = 0, length = 0;
    require(ipc_v1::grant_create(0, page_bytes, 1, denied, length) ==
            static_cast<i64>(ipc_v1_error::resources), "handle-quota");
    require(!ipc_v1::grant_release(handles[0]), "release-quota-credit");
    handles[0] = create(1);
    for (auto handle : handles) require(!ipc_v1::grant_release(handle), "quota-cleanup");
}
void fragments() {
    const auto handle = create();
    const u64 first = arena + 0x10000, second_map = arena + 0x20000;
    const u64 neighbors[] = {first - page_bytes, first + page_bytes, second_map - page_bytes, second_map + page_bytes};
    map(handle, first); map(handle, second_map);
    for (auto address : neighbors)
        require(vm(vm_operation::reserve, address) == static_cast<i64>(address), "neighbor-reserve");
    u64 reserved[300]{}; u32 count = 0;
    for (; count < 300; ++count) {
        const auto address = arena + 0x100000 + u64{count} * 0x3000;
        const auto result = vm(vm_operation::reserve, address);
        if (result == vm_error_resources) break;
        require(result == static_cast<i64>(address), "fragment-reserve", result); reserved[count] = address;
    }
    require(count > 2 && count < 300, "finite-fragment-budget");
    require(!vm(vm_operation::unmap, reserved[--count]), "free-one-fragment");
    // Each middle mapping needs a split. One free slot is insufficient for
    // both; failure must preserve the first mapping too.
    require(ipc_v1::grant_release(handle) == static_cast<i64>(ipc_v1_error::resources), "aggregate-preflight");
    readable(first); readable(second_map);
    require(!vm(vm_operation::unmap, reserved[--count]), "free-second-fragment");
    require(!ipc_v1::grant_release(handle), "aggregate-release-retry"); released(handle);
    for (u32 i = 0; i < count; ++i) require(!vm(vm_operation::unmap, reserved[i]), "fragment-cleanup");
    for (auto address : neighbors)
        require(!vm(vm_operation::unmap, address), "neighbor-cleanup");
    const auto fresh = create(); map(fresh, first); map(fresh, second_map);
    require(!ipc_v1::grant_release(fresh), "alias-reservations-reusable");
}
struct waiter_args { u64 notification, address; };
u64 waiter(void* raw) {
    auto* args = static_cast<waiter_args*>(raw);
    auto* request = reinterpret_cast<ipc_v1_notification_wait*>(args->address);
    *request = {}; request->handle = args->notification; request->deadline_ns = now() + 5 * second;
    return static_cast<u64>(ipc_v1::invoke(ipc_v1_action::notification_wait, *request));
}
void pinned() {
    const auto handle = create(); map(handle, arena); map(handle, arena + 0x10000);
    u64 notification = 0, signal = 0;
    require(!ipc_v1::notification_create(ipc_v1_notification_right_all, notification), "notification");
    require(!ipc_v1::notification_delegate(notification, sdk::pid(), 1,
            static_cast<u32>(ipc_v1_notification_right::signal), signal), "signal-right");
    waiter_args args{notification, arena + 128}; u64 tid = 0;
    require(!thread::create(tid, waiter, &args), "waiter-thread");
    bool observed = false; const auto limit = now() + second;
    while (now() < limit) {
        observe_native::request request{1, sizeof(request), observe_native::query::process, 0, 0, 0, 0, now() + second};
        observe_native::snapshot state{};
        require(sdk::observe(request, state) == observe_native::result::ok, "observe-blocked");
        if (state.threads == 2 && state.blocked_threads == 1) { observed = true; break; }
        sdk::yield();
    }
    require(observed, "actual-pin-wait-observed");
    require(ipc_v1::grant_release(handle) == static_cast<i64>(ipc_v1_error::busy), "pin-blocked-release");
    readable(arena); readable(arena + 0x10000);
    require(!ipc_v1::notification_signal(signal), "unpin-signal");
    u64 value = 1; require(!thread::join(tid, value) && !value, "waiter-join");
    require(reinterpret_cast<ipc_v1_notification_wait*>(arena + 128)->bits_out == 1, "pin-output-preserved");
    require(!ipc_v1::grant_release(handle) && !ipc_v1::notification_close(notification), "unpin-release-retry");
}
int child(u64 handle, const char* mode) {
    if (sdk::equal(mode, "foreign")) {
        require(ipc_v1::grant_release(handle) == invalid_handle, "foreign-release-denied"); return 0;
    }
    ipc_channel channel{}; require(!sdk::ipc_name_connect(name, channel), "child-connect");
    require(receive(channel) == 1, "delegate-barrier");
    u64 id = 0, length = 0;
    require(ipc_v1::grant_map(handle, arena, ipc_v1_grant_access::read_write, id, length) ==
            static_cast<i64>(ipc_v1_error::denied), "delegate-write-denied");
    map(handle, arena, ipc_v1_grant_access::read); readable(arena); send(channel, 1);
    require(receive(channel) == 2, "release-barrier");
    if (sdk::equal(mode, "owner_exit")) {
        send(channel, 2); // The exiting owner must not flush an unread barrier.
        const auto limit = now() + 5 * second;
        u64 peer = 0;
        while (!sdk::ipc_endpoint_peer(channel.send, peer)) { require(now() < limit, "owner-exit-deadline"); pause(); }
        readable(arena); require(!ipc_v1::grant_release(handle), "last-holder-after-owner-exit");
        sdk::print("GRANT_RELEASE_OWNER_EXIT_CHILD_PASS\n"); return 0;
    }
    readable(arena);
    if (sdk::equal(mode, "holder_exit")) return 0; // Exit retains the producer mapping.
    const auto before = budget();
    require(!ipc_v1::grant_release(handle), "child-local-release"); released(handle);
    const auto after = budget();
    require(after.attributed.ipc_objects == before.attributed.ipc_objects &&
            after.attributed.pages + 1 == before.attributed.pages, "delegate-does-not-own-budget-credit");
    send(channel, 2); require(receive(channel) == 3, "parent-budget-barrier"); return 0;
}
void cross_process(const char* mode) {
    require(!sdk::set_process_budget(sdk::pid(), {4, 2048, 4, 16, 4, 4}), "install-tree-budget");
    require(!sdk::ipc_name_publish(name), "publish");
    const auto handle = create(); map(handle, arena); map(handle, arena + 0x10000);
    char handle_text[24]{}; decimal(handle, handle_text);
    const char* arguments[] = {"child", handle_text, mode};
    const auto child_pid = sdk::spawn_file(binary, 3, arguments);
    require(child_pid > 0, "spawn-child", child_pid);
    sdk::print("GRANT_RELEASE_CHILD pid="); sdk::decimal(child_pid); sdk::print("\n");
    if (sdk::equal(mode, "foreign")) {
        process_status status{}; require(!sdk::wait(child_pid, status) && status.code == 0, "foreign-child");
        readable(arena); require(!ipc_v1::grant_release(handle), "foreign-cannot-revoke"); return;
    }
    u64 delegated = 0; require(!ipc_v1::grant_delegate(handle, child_pid, 1, delegated) && delegated == handle, "delegate");
    ipc_channel channel{}; require(!sdk::ipc_name_accept(channel), "accept");
    send(channel, 1); require(receive(channel) == 1, "child-mapped");
    const auto before = budget();
    if (sdk::equal(mode, "owner_exit")) {
        send(channel, 2); require(receive(channel) == 2, "owner-exit-armed"); sdk::exit(0);
    }
    const bool owner_first = sdk::equal(mode, "owner_first");
    if (owner_first) {
        require(!ipc_v1::grant_release(handle), "owner-local-release"); released(handle);
        const auto retained = budget();
        require(retained.attributed.ipc_objects == before.attributed.ipc_objects &&
                retained.attributed.pages + 2 == before.attributed.pages &&
                retained.usage.ipc_objects == before.usage.ipc_objects, "retained-original-owner-charge");
    }
    send(channel, 2);
    process_status status{};
    if (sdk::equal(mode, "holder_exit")) {
        require(!sdk::wait(child_pid, status) && status.code == 0, "holder-exit");
        readable(arena); readable(arena + 0x10000);
        require(!ipc_v1::grant_release(handle), "owner-after-holder-exit"); return;
    }
    require(receive(channel) == 2, "child-released");
    if (!owner_first) { readable(arena); readable(arena + 0x10000); require(!ipc_v1::grant_release(handle), "owner-last-release"); }
    const auto after = budget();
    require(after.attributed.ipc_objects + 1 == before.attributed.ipc_objects &&
            after.attributed.pages + 3 == before.attributed.pages &&
            after.usage.ipc_objects + 1 == before.usage.ipc_objects &&
            after.usage.pages + 4 == before.usage.pages, "last-reference-budget-recovery");
    send(channel, 3);
    require(!sdk::wait(child_pid, status) && status.outcome == process_outcome::exited && !status.code, "child-exit");
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc == 3 && sdk::equal(args[0], "child")) return child(number(args[1]), args[2]);
    require(startup->argc == 2, "usage");
    const auto* mode = args[1];
    if (sdk::equal(mode, "features")) features();
    else if (sdk::equal(mode, "quota")) quota();
    else if (sdk::equal(mode, "fragments")) fragments();
    else if (sdk::equal(mode, "pinned")) pinned();
    else cross_process(mode);
    sdk::print("GRANT_RELEASE_PASS "); sdk::print(mode); sdk::print("\n"); return 0;
}
