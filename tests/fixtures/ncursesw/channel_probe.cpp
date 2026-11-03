// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include <xos/thread_abi.hpp>
using namespace xos;

namespace {
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic, 3, sizeof(exec_marker)};
}

static u64 deadline() {
    return static_cast<u64>(sdk::syscall(sys_clock_monotonic)) + 3000000000ull;
}

// sys_tasklist exposes process state. The protocol below ensures that after
// the second handshake the parent has no other blocking operation pending.
static bool process_waiting(u64 pid) {
    char buffer[768]{};
    const i64 length = sdk::syscall(9, reinterpret_cast<u64>(buffer), sizeof(buffer));
    if (length <= 0 || length > static_cast<i64>(sizeof(buffer))) return false;
    char digits[24]{};
    u32 count = 0;
    do { digits[count++] = static_cast<char>('0' + pid % 10); pid /= 10; } while (pid != 0);
    for (u32 i = 0; i + 4 + count < static_cast<u32>(length); ++i) {
        if (buffer[i] != 'p' || buffer[i + 1] != 'i' || buffer[i + 2] != 'd' || buffer[i + 3] != '=') continue;
        bool match = true;
        for (u32 j = 0; j < count; ++j) if (buffer[i + 4 + j] != digits[count - 1 - j]) match = false;
        u32 at = i + 4 + count;
        if (!match || buffer[at] != ' ') continue;
        while (at + 8 < static_cast<u32>(length) && buffer[at] != '\n') {
            if (buffer[at] == ' ' && buffer[at + 1] == 's' && buffer[at + 2] == 't' &&
                buffer[at + 3] == 'a' && buffer[at + 4] == 't' && buffer[at + 5] == 'e' &&
                buffer[at + 6] == '=' && buffer[at + 7] == 'W') return true;
            ++at;
        }
        return false;
    }
    return false;
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
        // The second spare channel is now ordinal 2. Its sender closes it
        // only after acknowledging the parent's single-channel wait request.
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 's' ||
            sdk::channel_get(2, extra) != 0 || extra.rights != channel_send) return 65;
        byte = 'r';
        if (sdk::ipc_send(out, &byte, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'w') return 66;
        const u64 wait_until = deadline();
        while (!process_waiting(first.peer_pid)) {
            if (static_cast<u64>(sdk::syscall(sys_clock_monotonic)) >= wait_until) return 69;
            sdk::yield();
        }
        if (sdk::channel_close(extra.handle) != 0) return 70;
        // The parent creates a parent-to-child spare and fills its one-slot
        // queue. Close only after observing the parent blocked waiting to send.
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'u' ||
            sdk::channel_get(2, extra) != 0 || extra.rights != channel_receive) return 72;
        byte = 'r';
        if (sdk::ipc_send(out, &byte, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'w') return 73;
        const u64 send_wait_until = deadline();
        while (!process_waiting(first.peer_pid)) {
            if (static_cast<u64>(sdk::syscall(sys_clock_monotonic)) >= send_wait_until) return 74;
            sdk::yield();
        }
        if (sdk::channel_close(extra.handle) != 0) return 75;
        if (sdk::channel_wait(in, deadline()) != 0 || sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'p') return 38;
        channel_info derived_send{}, derived_receive{};
        if (sdk::channel_get(2, derived_send) != 0 || sdk::channel_get(3, derived_receive) != 0 ||
            derived_send.peer_pid == first.peer_pid || derived_send.peer_pid != derived_receive.peer_pid ||
            derived_send.controller_pid != first.controller_pid ||
            derived_receive.controller_pid != first.controller_pid ||
            derived_send.rights == derived_receive.rights) return 39;
        const u32 derived_in = derived_send.rights == channel_receive ? derived_send.handle : derived_receive.handle;
        const u32 derived_out = derived_send.rights == channel_send ? derived_send.handle : derived_receive.handle;
        channel_fork_verification verification{channel_version, sizeof(channel_fork_verification),
                                               in, out, derived_in, derived_out, derived_send.peer_pid};
        if (sdk::channel_verify_fork(verification) != 0) return 62;
        verification.child_incoming = derived_out;
        if (sdk::channel_verify_fork(verification) != process_error_denied) return 63;
        verification.child_incoming = derived_in;
        verification.child_pid = first.peer_pid;
        if (sdk::channel_verify_fork(verification) != process_error_denied) return 64;
        byte = 'v';
        if (sdk::ipc_send(out, &byte, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &byte, 1) != 1 || byte != 't') return 40;
        if (sdk::channel_get(2, derived_send) != 0 || sdk::channel_get(3, derived_receive) != 0 ||
            derived_send.peer_pid != derived_receive.peer_pid || derived_send.peer_pid == first.peer_pid ||
            derived_send.rights == derived_receive.rights) return 51;
        const u32 child_in = derived_send.rights == channel_receive ? derived_send.handle : derived_receive.handle;
        const u32 child_out = derived_send.rights == channel_send ? derived_send.handle : derived_receive.handle;
        byte = 'v';
        if (sdk::ipc_send(out, &byte, 1) != 0 || sdk::channel_wait(child_in, deadline()) != 0 ||
            sdk::ipc_recv(child_in, &byte, 1) != 1 || byte != 'x') return 52;
        byte = 'y';
        if (sdk::ipc_send(child_out, &byte, 1) != 0 || sdk::channel_wait(in, deadline()) != 0 ||
            sdk::ipc_recv(in, &byte, 1) != 1 || byte != 'c' ||
            sdk::channel_get(2, extra) != thread_error_not_found) return 53;
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
    if (sdk::channel_wait(extra[0], 0) != process_error_denied) return 18;
    const char single_wait_request = 's';
    if (sdk::ipc_send(outgoing, &single_wait_request, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'r') return 67;
    const char entering_wait = 'w';
    if (sdk::ipc_send(outgoing, &entering_wait, 1) != 0) return 71;
    if (sdk::channel_wait(extra[1], deadline()) != process_error_denied ||
        sdk::channel_wait(extra[1], 0) != process_error_denied) return 68;
    request.sender_pid = sdk::pid(); request.receiver_pid = child;
    const i64 spare_send = sdk::channel_open(request);
    if (spare_send <= 0) return 76;
    const char prepare_send_wait = 'u';
    if (sdk::ipc_send(outgoing, &prepare_send_wait, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'r') return 77;
    const char queued = 'q';
    if (sdk::ipc_send(static_cast<u32>(spare_send), &queued, 1) != 0 ||
        sdk::channel_wait(static_cast<u32>(spare_send), 0) != process_error_would_block ||
        sdk::ipc_send(outgoing, &entering_wait, 1) != 0) return 78;
    if (sdk::channel_wait(static_cast<u32>(spare_send), deadline()) != process_error_denied ||
        sdk::channel_wait(static_cast<u32>(spare_send), 0) != process_error_denied) return 79;
    const i64 forked = sdk::syscall(sys_process_fork_prepare);
    if (forked <= 0) return 41;
    channel_fork_pair rejected{channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked),
                               incoming, outgoing, 0, 0};
    if (sdk::channel_fork(rejected) != process_error_denied || rejected.child_send != 0 ||
        rejected.child_receive != 0) return 46;
    rejected = {channel_version, sizeof(channel_fork_pair), child, outgoing, incoming, 0, 0};
    if (sdk::channel_fork(rejected) != process_error_denied) return 47;
    rejected = {channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked), outgoing, outgoing, 0, 0};
    if (sdk::channel_fork(rejected) != process_error_invalid) return 48;
    rejected = {channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked), outgoing, incoming, 1, 0};
    if (sdk::channel_fork(rejected) != process_error_invalid) return 49;
    rejected = {channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked), outgoing, 0xffffffffu, 0, 0};
    if (sdk::channel_fork(rejected) != process_error_denied) return 50;
    channel_fork_pair pair{channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked),
                           outgoing, incoming, 0, 0};
    if (sdk::channel_fork(pair) != 0 || pair.child_send == 0 || pair.child_receive == 0 ||
        pair.child_send == pair.child_receive || sdk::channel_wait(pair.child_send, 0) != process_error_denied)
        return 42;
    channel_fork_pair duplicate{channel_version, sizeof(channel_fork_pair), static_cast<u64>(forked),
                                outgoing, incoming, 0, 0};
    if (sdk::channel_fork(duplicate) != process_error_state || duplicate.child_send != 0 ||
        duplicate.child_receive != 0) return 43;
    const char inspect = 'p';
    if (sdk::ipc_send(outgoing, &inspect, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'v') return 44;
    if (sdk::syscall(sys_process_abort, static_cast<u64>(forked)) != 0) return 45;
    const i64 running_child = sdk::syscall(sys_process_fork_prepare);
    if (running_child == 0) {
        channel_info a{}, b{};
        if (sdk::channel_get(0, a) != 0 || sdk::channel_get(1, b) != 0 ||
            a.peer_pid != b.peer_pid || a.rights == b.rights) return 54;
        const u32 send = a.rights == channel_send ? a.handle : b.handle;
        const u32 receive = a.rights == channel_receive ? a.handle : b.handle;
        char value = 'x';
        if (sdk::ipc_send(send, &value, 1) != 0 || sdk::channel_wait(receive, deadline()) != 0 ||
            sdk::ipc_recv(receive, &value, 1) != 1 || value != 'y') return 55;
        return 0;
    }
    if (running_child < 0) return 56;
    channel_fork_pair running_pair{channel_version, sizeof(channel_fork_pair), static_cast<u64>(running_child),
                                   outgoing, incoming, 0, 0};
    if (sdk::channel_fork(running_pair) != 0) return 57;
    const char inspect_running = 't';
    if (sdk::ipc_send(outgoing, &inspect_running, 1) != 0 || sdk::channel_wait(incoming, deadline()) != 0 ||
        sdk::ipc_recv(incoming, &response, 1) != 1 || response != 'v') return 58;
    file::Client files{};
    if (!files.init()) return 59;
    i64 cloned = static_cast<i64>(file::status::would_block);
    for (u32 attempt = 0; attempt < 128 && cloned == static_cast<i64>(file::status::would_block); ++attempt) {
        cloned = files.clone_session(static_cast<u64>(running_child));
        if (cloned == static_cast<i64>(file::status::would_block)) sdk::yield();
    }
    if (cloned != 0 || sdk::syscall(sys_process_fork_commit, static_cast<u64>(running_child)) != 0) return 60;
    process_status child_status{};
    if (sdk::wait(static_cast<u64>(running_child), child_status) != 0 ||
        child_status.outcome != process_outcome::exited || child_status.code != 0) return 61;
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
