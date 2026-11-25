// SPDX-License-Identifier: Apache-2.0
// Native guest fixture: use the public wire protocol, authenticated IPC and
// existing process lifecycle APIs. No libc implementation is linked.
#include <xos/net_transport.hpp>

namespace {
using namespace xos;
using namespace xos::net2;
struct output_line {
    char bytes[256]{};
    u32 size = 0;
    void text(const char* value) { while (*value && size + 1 < sizeof(bytes)) bytes[size++] = *value++; }
    void number(u64 value) {
        char digits[21]; u32 count = 0;
        do { digits[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
        while (count && size + 1 < sizeof(bytes)) bytes[size++] = digits[--count];
    }
    void finish() { text("\n"); (void)sdk::write(1, bytes, size); }
};
[[noreturn]] void fail(const char* label, i64 value) {
    output_line out; out.text("NET_LIFECYCLE_FAIL "); out.text(label); out.text(" result=");
    if (value < 0) { out.text("-"); out.number(static_cast<u64>(-value)); }
    else out.number(static_cast<u64>(value));
    out.finish(); sdk::exit(91);
}
void require(bool condition, const char* label, i64 value = 0) { if (!condition) fail(label, value); }
u64 now() {
    const i64 value = sdk::syscall(sys_clock_monotonic);
    require(value >= 0, "clock", value); return static_cast<u64>(value);
}
void sleep_ns(u64 duration) {
    const i64 result = sdk::syscall(sys_sleep_until, now() + duration);
    require(!result, "sleep", result);
}
u64 decimal(const char* text) {
    require(text && *text, "number-empty"); u64 value = 0;
    while (*text) {
        require(*text >= '0' && *text <= '9', "number-character");
        const u64 digit = static_cast<u64>(*text++ - '0');
        require(value <= (~u64{0} - digit) / 10, "number-overflow"); value = value * 10 + digit;
    }
    return value;
}
void marker(const char* name, u64 first = 0, u64 second = 0) {
    output_line out; out.text(name); out.text(" pid="); out.number(sdk::pid());
    out.text(" first="); out.number(first); out.text(" second="); out.number(second); out.finish();
}
class raw_client {
public:
    ipc_channel channel{};
    u64 sequence = 0;
    ~raw_client() { close(); }
    i64 connect(u64 expected) {
        const i64 result = sdk::ipc_name_connect(service_name, channel);
        if (result) return result;
        u64 outgoing = 0, incoming = 0;
        if (sdk::ipc_endpoint_peer(channel.send, outgoing) || sdk::ipc_endpoint_peer(channel.receive, incoming) ||
            outgoing != expected || incoming != expected) { close(); return denied; }
        return 0;
    }
    void close() {
        if (channel.send) (void)sdk::ipc_channel_close(channel.send);
        if (channel.receive) (void)sdk::ipc_channel_close(channel.receive);
        channel = {}; sequence = 0;
    }
    void send(message& input) {
        input.version = version; input.sequence = ++sequence;
        if (!input.deadline) input.deadline = now() + 5'000'000'000ull;
        for (;;) {
            const i64 result = sdk::ipc_send(channel.send, &input, header_bytes + input.length);
            if (!result) return;
            require(result == ipc_error_full && now() < input.deadline, "request-send", result);
            sleep_ns(1'000'000);
        }
    }
    i64 receive(const message& input, message& reply) {
        for (;;) {
            const i64 result = sdk::ipc_recv(channel.receive, &reply, sizeof(reply));
            if (result != -3) {
                if (result < 0) return result;
                require(result >= header_bytes && reply.version == version && reply.action == input.action &&
                        reply.sequence == input.sequence && reply.length <= payload_bytes &&
                        static_cast<u64>(result) == header_bytes + reply.length && !reply.reserved &&
                        !reply.deadline && !reply.address && !reply.port && reply.transport == protocol::none,
                        "reply-identity-or-shape", result);
                return reply.result;
            }
            require(now() < input.deadline, "request-timeout"); sleep_ns(1'000'000);
        }
    }
    i64 request(message& input, message& reply) { send(input); return receive(input, reply); }
    information info() {
        message input{}, reply{}; input.action = operation::information;
        const i64 result = request(input, reply);
        require(!result && reply.length == sizeof(information) && !reply.object && !reply.flags, "information", result);
        information value{}; __builtin_memcpy(&value, reply.data, sizeof(value));
        require(value.max_sessions == client_sessions && value.max_connections == connection_limit &&
                value.max_payload == payload_bytes && value.max_per_session == connections_per_session &&
                !value.reserved, "information-limits");
        return value;
    }
    u64 open_udp(u16 port = 9) {
        message input{}, reply{}; input.action = operation::open; input.address = permitted_address;
        input.port = port; input.transport = protocol::udp;
        const i64 result = request(input, reply);
        require(!result && reply.object && reply.flags == connected, "open-udp", result); return reply.object;
    }
    u64 wait_closed(u64 limit) {
        const u64 began = now();
        for (;;) {
            const i64 result = sdk::ipc_wait(channel.send, ipc_wait_mode::try_send);
            if (result == ipc_error_broken || result == process_error_denied) return now() - began;
            require(result == 0 || result == process_error_would_block, "channel-ready", result);
            require(now() - began < limit, "channel-not-closed"); sleep_ns(5'000'000);
        }
    }
};
void denied_controls(raw_client& client, u64 victim_handle, u64 victim_pid) {
    constexpr operation object_actions[]{operation::status, operation::receive, operation::send, operation::close, operation::cancel};
    for (const operation action : object_actions) {
        message input{}, reply{}; input.action = action; input.object = victim_handle;
        if (action == operation::receive) input.flags = 32;
        if (action == operation::send) { input.length = 1; input.data[0] = 0x7a; }
        const i64 result = client.request(input, reply);
        require(result == denied && !reply.length, "foreign-handle-denied", result);
    }
    constexpr operation control_actions[]{operation::revoke_peer, operation::stop};
    for (const operation action : control_actions) {
        message input{}, reply{}; input.action = action;
        if (action == operation::revoke_peer) input.object = victim_pid;
        const i64 result = client.request(input, reply);
        require(result == denied && !reply.length, "controller-operation-denied", result);
    }
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    require(startup && startup->magic == startup_magic && startup->argc >= 3, "startup");
    const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
    const u64 service = decimal(argv[2]);
    raw_client client; const i64 connected_result = client.connect(service);
    require(!connected_result, "connect", connected_result);
    (void)client.info();
    if (sdk::equal(argv[1], "info")) {
        const auto info = client.info(); marker("NET_INFO_PASS", info.sessions, info.connections); return 0;
    }
    if (sdk::equal(argv[1], "isolation")) {
        require(startup->argc == 5, "isolation-arguments");
        denied_controls(client, decimal(argv[3]), decimal(argv[4]));
        marker("NET_ISOLATION_PASS"); return 0;
    }
    const u16 port = startup->argc > 3 ? static_cast<u16>(decimal(argv[3])) : 9;
    const u64 handle = client.open_udp(port);
    if (sdk::equal(argv[1], "hold")) {
        const u64 second = client.open_udp(port);
        message input{}, reply{}; input.action = operation::open; input.address = permitted_address;
        input.port = port; input.transport = protocol::udp;
        const i64 result = client.request(input, reply);
        require(result == resources && !reply.object, "per-session-budget", result);
        marker("NET_HOLD_READY", handle, second);
        for (u32 tick = 0; tick < 120; ++tick) { sleep_ns(1'000'000'000); (void)client.info(); }
        fail("hold-not-terminated", 0);
    }
    if (sdk::equal(argv[1], "pending")) {
        require(startup->argc == 5 && sdk::length(argv[4]) == 32, "pending-arguments");
        message input{}, reply{}; input.action = operation::send; input.object = handle; input.length = 32;
        __builtin_memcpy(input.data, argv[4], 32);
        require(client.request(input, reply) == 32, "pending-send");
        // The host withholds the only echo until this negative control has
        // observed an empty UDP queue. A readable IPC endpoint alone is not
        // evidence of a payload: would_block replies are readable too.
        input = {}; input.action = operation::receive; input.object = handle; input.flags = 31;
        const i64 empty = client.request(input, reply);
        require(empty == would_block && !reply.length && !reply.flags, "pending-empty", empty);
        marker("NET_PENDING_EMPTY", handle);
        // UDP's existing short-buffer result retains the complete datagram.
        // No other request consumes this connection's sole 32-byte nonce.
        const u64 echo_deadline = now() + 5'000'000'000ull;
        for (;;) {
            input = {}; input.action = operation::receive; input.object = handle; input.flags = 31;
            input.deadline = echo_deadline;
            const i64 got = client.request(input, reply);
            if (got == would_block) { sleep_ns(1'000'000); continue; }
            require(got == buffer_too_small && !reply.length && reply.flags == 32 && reply.object == handle,
                    "pending-datagram-retained", got);
            break;
        }
        const u64 pending_began = now();
        input = {}; input.action = operation::receive; input.object = handle; input.flags = 32; client.send(input);
        for (;;) {
            const i64 ready = sdk::ipc_wait(client.channel.receive, ipc_wait_mode::try_receive);
            if (!ready) break;
            require(ready == process_error_would_block && now() < input.deadline, "pending-reply-timeout", ready);
            sleep_ns(1'000'000);
        }
        // Legacy sys5 rejects a short output buffer before copying or consuming
        // the queued message. Only the successful receive can have 96 bytes;
        // all errors above have the 64-byte header and would be consumed here.
        __builtin_memset(&reply, 0xa5, sizeof(reply));
        const i64 short_read = sdk::ipc_recv(client.channel.receive, &reply, header_bytes + 31);
        require(short_read == -2, "pending-payload-not-header", short_read);
        const auto* untouched = reinterpret_cast<const u8*>(&reply);
        for (u32 i = 0; i < sizeof(reply); ++i) require(untouched[i] == 0xa5, "pending-buffer-unchanged");
        require(!sdk::ipc_wait(client.channel.receive, ipc_wait_mode::try_receive), "pending-still-queued");
        marker("NET_PENDING_READY", handle, header_bytes + 32);
        (void)client.wait_closed(5'000'000'000ull);
        const u64 revoked_after = now() - pending_began;
        require(revoked_after < reply_timeout_ns, "pending-revoked-before-timeout", revoked_after);
        client.close();
        // A fresh IPC pair can be allocated before admission; the first
        // authenticated reply must still fail for a revoked PID.
        const i64 reconnected = client.connect(service);
        if (!reconnected) {
            input = {}; input.version = version; input.sequence = 1; input.action = operation::information;
            input.deadline = now() + 5'000'000'000ull;
            const i64 sent = sdk::ipc_send(client.channel.send, &input, header_bytes);
            const i64 result = sent ? sent : client.receive(input, reply);
            require(result == ipc_error_broken || result == -1 || result == process_error_denied,
                    "revoked-pid-reconnected", result);
        }
        marker("NET_REVOKED_PASS", revoked_after); return 0;
    }
    if (sdk::equal(argv[1], "stall")) {
        message input{}; input.action = operation::information; client.send(input);
        const u64 elapsed = client.wait_closed(2'000'000'000ull);
        require(elapsed >= reply_timeout_ns && elapsed < 2'000'000'000ull, "reply-timeout-bound", elapsed);
        marker("NET_STALL_PASS", elapsed); return 0;
    }
    if (sdk::equal(argv[1], "idle")) {
        const u64 elapsed = client.wait_closed(idle_ns + 5'000'000'000ull);
        require(elapsed + 100'000'000 >= idle_ns, "idle-timeout-too-early", elapsed);
        marker("NET_IDLE_PASS", elapsed); return 0;
    }
    if (sdk::equal(argv[1], "service_lost")) {
        marker("NET_SERVICE_READY", handle);
        (void)client.wait_closed(10'000'000'000ull);
        marker("NET_SERVICE_LOST_PASS"); return 0;
    }
    if (sdk::equal(argv[1], "exit")) { marker("NET_EXIT_READY", handle); sdk::exit(0); }
    if (sdk::equal(argv[1], "fault")) { marker("NET_FAULT_READY", handle); __builtin_trap(); }
    if (sdk::equal(argv[1], "cancel")) {
        message input{}, reply{}; input.action = operation::cancel; input.object = handle;
        require(client.request(input, reply) == 0, "cancel");
        input = {}; input.action = operation::status; input.object = handle;
        require(client.request(input, reply) == closed, "cancelled-handle-closed");
        require(client.info().connections == 0, "cancel-reclaims");
        marker("NET_CANCEL_PASS"); return 0;
    }
    if (sdk::equal(argv[1], "exec")) {
        marker("NET_EXEC_READY", handle);
        sdk::spawn_options options{}; options.replace_image = true;
        const char* arguments[]{"/bin/netexec.elf", argv[2]};
        fail("exec-returned", sdk::spawn_file_options(arguments[0], 2, arguments, options));
    }
    fail("mode", 0);
}
