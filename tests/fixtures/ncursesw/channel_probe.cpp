// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
using namespace xos;

static u64 deadline() {
    return static_cast<u64>(sdk::syscall(sys_clock_monotonic)) + 3000000000ull;
}

extern "C" int xos_user_main(const startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc > 1 && sdk::equal(args[1], "child")) {
        channel_info first{}, second{};
        const u64 until = sdk::ticks() + 300;
        while (sdk::channel_get(0, first) != 0 || sdk::channel_get(1, second) != 0) {
            if (sdk::ticks() >= until) return 1;
            sdk::yield();
        }
        if (first.peer_pid != second.peer_pid || first.controller_pid != second.controller_pid ||
            first.peer_pid != first.controller_pid || first.rights == second.rights) return 2;
        const u32 in = first.rights == channel_receive ? first.handle : second.handle;
        const u32 out = first.rights == channel_send ? first.handle : second.handle;
        if (sdk::channel_wait(in, deadline()) != 0) return 3;
        char byte = 0;
        if (sdk::ipc_recv(in, &byte, 0) != process_error_invalid) return 19;
        // An undersized receive must leave the pending byte available.
        if (sdk::channel_wait(in, 0) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'a') return 4;
        byte = 'b';
        if (sdk::ipc_send(out, &byte, 1) != 0) return 5;
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'c') return 6;
        return 0;
    }
    channel_create invalid{channel_version, sizeof(channel_create), sdk::pid(), ~u64{0}, 1, 0};
    if (sdk::channel_open(invalid) != process_error_denied) return 7;
    const char* child_args[] = {"channel", "child"};
    const i64 pid = sdk::spawn_file("/bin/channel.elf", 2, child_args);
    if (pid <= 0) return 8;
    const u64 child = static_cast<u64>(pid);
    channel_create request{channel_version, sizeof(channel_create), sdk::pid(), child, 1, 0};
    const i64 to_child = sdk::channel_open(request);
    request.sender_pid = child; request.receiver_pid = sdk::pid();
    const i64 from_child = sdk::channel_open(request);
    if (to_child <= 0 || from_child <= 0) return 9;
    const u32 outgoing = static_cast<u32>(to_child), incoming = static_cast<u32>(from_child);
    if (sdk::channel_wait(incoming, 0) != process_error_would_block) return 10;
    // Exhaust only this controller's quota; the child remains alive waiting.
    u32 extra[2]{};
    for (u32 i = 0; i < 2; ++i) {
        const i64 handle = sdk::channel_open(request);
        if (handle <= 0) return 16;
        extra[i] = static_cast<u32>(handle);
    }
    if (sdk::channel_open(request) != process_error_resources) return 17;
    for (auto handle : extra) {
        if (sdk::channel_close(handle) != 0 ||
            sdk::channel_wait(handle, 0) != process_error_denied) return 18;
    }
    const char first = 'a';
    if (sdk::ipc_send(outgoing, &first, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0) return 11;
    char response = 0;
    if (sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'b') return 12;
    const char last = 'c';
    if (sdk::ipc_send(outgoing, &last, 1) != 0) return 13;
    process_status status{};
    if (sdk::wait(child, status) != 0 || status.outcome != process_outcome::exited || status.code != 0) return 14;
    if (sdk::channel_wait(incoming, 0) != process_error_denied) return 15;
    sdk::print("W1_CHANNEL_OK\n");
    return 0;
}
