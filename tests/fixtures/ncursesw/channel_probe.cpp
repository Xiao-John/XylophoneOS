// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
using namespace xos;

namespace {
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
}

static u64 deadline() {
    return static_cast<u64>(sdk::syscall(sys_clock_monotonic)) + 3000000000ull;
}

extern "C" int xos_user_main(const startup_info* startup) {
    const auto args = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc > 1 && sdk::equal(args[1], "replaced")) {
        channel_info first{}, second{};
        if (sdk::channel_get(0, first) != 0 || sdk::channel_get(1, second) != 0 ||
            first.rights == second.rights || first.peer_pid != second.peer_pid) return 20;
        const u32 out = first.rights == channel_send ? first.handle : second.handle;
        const u32 in = first.rights == channel_receive ? first.handle : second.handle;
        const char done = 'd';
        char acknowledgment = 0;
        if (sdk::ipc_send(out, &done, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &acknowledgment, 1) != 1 || acknowledgment != 'h') return 21;
        return 0;
    }
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
        // Give the parent a bounded interval to enter wait_many, then close
        // one of the two receive endpoints in that wait set.
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'k') return 33;
        channel_info extra{};
        if (sdk::channel_get(2, extra) != 0 || extra.rights != channel_send ||
            extra.peer_pid != first.peer_pid || extra.controller_pid != first.controller_pid) return 34;
        byte = 'r';
        if (sdk::ipc_send(out, &byte, 1) != 0 ||
            sdk::syscall(sys_sleep_until, static_cast<u64>(sdk::syscall(sys_clock_monotonic)) + 100000000ull) != 0 ||
            sdk::channel_close(extra.handle) != 0) return 35;
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'c') return 6;
        sdk::spawn_options options{};
        options.replace_image = true;
        const char* replacement[] = {"channel", "replaced"};
        const u32 bad[] = {in, in};
        options.exec_channel_count = 2; options.exec_channels = bad;
        if (sdk::spawn_file_options("/bin/channel.elf", 2, replacement, options) != process_error_invalid) return 22;
        const char failed = 'f';
        if (sdk::ipc_send(out, &failed, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'g') return 23;
        const u32 kept[] = {in, out};
        options.exec_channels = kept;
        (void)sdk::spawn_file_options("/bin/channel.elf", 2, replacement, options);
        return 24; // successful exec does not return
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
    channel_wait_many_request many{channel_version, sizeof(channel_wait_many_request), 2, 0,
                                   {incoming, extra[0], 0, 0}};
    if (sdk::channel_wait_many(many, 0) != process_error_would_block) return 28;
    const u64 timeout = static_cast<u64>(sdk::syscall(sys_clock_monotonic)) + 30000000ull;
    if (sdk::channel_wait_many(many, timeout) != thread_error_timeout) return 29;
    many.handles[1] = incoming;
    if (sdk::channel_wait_many(many, 0) != process_error_invalid) return 30;
    many.handles[0] = outgoing; many.handles[1] = 0xffffffffu;
    if (sdk::channel_wait_many(many, 0) != process_error_denied) return 31;
    many.handles[0] = incoming; many.handles[1] = extra[0];
    const char first = 'a';
    if (sdk::ipc_send(outgoing, &first, 1) != 0) return 11;
    i64 ready = 0;
    const u64 until = deadline();
    do { ready = sdk::channel_wait_many(many, until); } while (ready == 0);
    if (ready != 1) return 32;
    char response = 0;
    if (sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'b') return 12;
    const char close_request = 'k';
    if (sdk::ipc_send(outgoing, &close_request, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'r') return 36;
    if (sdk::channel_wait_many(many, deadline()) != 0 ||
        sdk::channel_wait_many(many, 0) != process_error_denied) return 37;
    if (sdk::channel_wait(extra[0], 0) != process_error_denied || sdk::channel_close(extra[1]) != 0 ||
        sdk::channel_wait(extra[1], 0) != process_error_denied) return 18;
    const char last = 'c';
    if (sdk::ipc_send(outgoing, &last, 1) != 0) return 13;
    if (sdk::channel_wait(incoming, deadline()) != 0 || sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'f') return 25;
    const char proceed = 'g';
    if (sdk::ipc_send(outgoing, &proceed, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'd') return 26;
    const char acknowledged = 'h';
    if (sdk::ipc_send(outgoing, &acknowledged, 1) != 0) return 27;
    process_status status{};
    if (sdk::wait(child, status) != 0 || status.outcome != process_outcome::exited || status.code != 0) return 14;
    if (sdk::channel_wait(incoming, 0) != process_error_denied) return 15;
    sdk::print("W1_CHANNEL_OK\n");
    return 0;
}
