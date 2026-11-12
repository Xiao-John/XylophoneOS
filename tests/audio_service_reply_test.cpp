// SPDX-License-Identifier: Apache-2.0
// Host test for audio_service response handling. Two contracts matter here:
// sdk::ipc_send reports success as 0 (not as a byte count), and revoking an
// endpoint drops a reply the peer has not read yet, so an active teardown
// must drain the reply within a bounded budget first.
#include <cstdio>
#include <cstring>

#include "../src/user/programs/audio_service.cpp"

namespace {
// Single-slot generic endpoints keyed by handle, mirroring the kernel model.
constexpr xos::u32 send_handle = 101;    // service -> peer reply endpoint
constexpr xos::u32 receive_handle = 102; // peer -> service request endpoint
// sys_send/sys_recv only exist in the kernel header; mirror their numbers.
constexpr xos::u64 fake_sys_send = 4, fake_sys_recv = 5;

struct fake_endpoint {
    bool used = false;
    bool pending = false;
    xos::u8 data[1024]{};
    xos::u32 length = 0;
};

struct fake_kernel {
    fake_endpoint endpoints[4];
    xos::u64 now_ns = 0;
    xos::u32 poll_count = 0;
    xos::i32 read_after_polls = -1; // -1: the peer never drains the reply
    xos::i64 send_error = 0;        // non-zero: every send fails with this
    xos::u8 request[544]{};
    xos::i64 request_result = -3;   // sys_error_empty until a test scripts it
    xos::u8 last_reply[64]{};
    xos::u32 last_reply_size = 0;
    bool revoked_while_pending = false;
    xos::u32 close_calls = 0;

    // spawn_buffer_options records, so the worker digest gate can be driven
    // without a loader.
    xos::u32 spawn_calls = 0;
    xos::i64 spawn_result = 5001;
    const char* spawn_name = nullptr;
    xos::u64 spawn_size = 0;
    xos::u32 spawn_argc = 0;

    fake_endpoint* find(xos::u32 handle) {
        if (handle == send_handle) return &endpoints[0];
        if (handle == receive_handle) return &endpoints[1];
        return nullptr;
    }
} kernel;

void reset_kernel() {
    kernel = fake_kernel{};
    kernel.endpoints[0].used = true;
    kernel.endpoints[1].used = true;
    sessions[0] = {};
    overflow_session = {};
    current_job = {};
    sessions[0].used = true;
    sessions[0].channel = {send_handle, receive_handle};
    sessions[0].peer_pid = 7;
    sessions[0].state = job_state::none;
}

xos::audio::request make_request(xos::u32 operation_value) {
    xos::audio::request message{};
    message.version = xos::audio::protocol_version;
    message.size = sizeof(message);
    message.operation = operation_value;
    return message;
}

void script_request(const xos::audio::request& message) {
    std::memcpy(kernel.request, &message, sizeof(message));
    kernel.request_result = static_cast<xos::i64>(sizeof(message));
}

bool reply_matches(xos::i64 expected_result) {
    if (kernel.last_reply_size != sizeof(xos::audio::response)) return false;
    xos::audio::response reply{};
    std::memcpy(&reply, kernel.last_reply, sizeof(reply));
    return reply.version == xos::audio::protocol_version &&
        reply.size == sizeof(reply) && reply.result == expected_result;
}
}

namespace xos::sdk {
// Host stubs for the syscalls audio_service uses; the kernel model above
// implements send/recv/wait/close/clock/sleep semantics.
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == sys_clock_monotonic) return static_cast<i64>(kernel.now_ns);
    if (number == sys_sleep_until) {
        if (first > kernel.now_ns) kernel.now_ns = first;
        return 0;
    }
    if (number == fake_sys_send) {
        fake_endpoint* endpoint = kernel.find(static_cast<u32>(first));
        if (endpoint == nullptr || !endpoint->used) return -1; // invalid handle
        if (kernel.send_error != 0) return kernel.send_error;
        if (endpoint->pending) return -4; // full: the previous reply is unread
        if (second == 0 || third == 0 || third > sizeof(endpoint->data)) return -2;
        std::memcpy(endpoint->data, reinterpret_cast<const void*>(second), third);
        endpoint->length = static_cast<u32>(third);
        endpoint->pending = true;
        kernel.last_reply_size = third < sizeof(kernel.last_reply)
            ? static_cast<u32>(third) : static_cast<u32>(sizeof(kernel.last_reply));
        std::memcpy(kernel.last_reply, reinterpret_cast<const void*>(second),
                    kernel.last_reply_size);
        return 0;
    }
    if (number == fake_sys_recv) {
        fake_endpoint* endpoint = kernel.find(static_cast<u32>(first));
        if (endpoint == nullptr || !endpoint->used) return -1;
        if (kernel.request_result <= 0) return kernel.request_result;
        if (second == 0 || third < sizeof(kernel.request)) return -2;
        std::memcpy(reinterpret_cast<void*>(second), kernel.request, sizeof(kernel.request));
        return kernel.request_result;
    }
    if (number == sys_ipc_wait) {
        fake_endpoint* endpoint = kernel.find(static_cast<u32>(first));
        if (endpoint == nullptr || !endpoint->used || third != 0) return -1; // denied
        if (second != static_cast<u64>(ipc_wait_mode::try_send)) return -2;
        if (!endpoint->pending) return 0;
        ++kernel.poll_count;
        if (kernel.read_after_polls >= 0 &&
            kernel.poll_count >= static_cast<u32>(kernel.read_after_polls)) {
            endpoint->pending = false; // the peer drained the reply
            return 0;
        }
        return -3; // still queued
    }
    if (number == sys_ipc_endpoint) {
        if (static_cast<ipc_endpoint_action>(first) != ipc_endpoint_action::close || third != 0)
            return -1;
        // The kernel revokes every endpoint of the channel together with any
        // message still queued in them.
        if (kernel.endpoints[0].pending || kernel.endpoints[1].pending)
            kernel.revoked_while_pending = true;
        if (kernel.endpoints[0].used || kernel.endpoints[1].used) ++kernel.close_calls;
        kernel.endpoints[0].used = false;
        kernel.endpoints[1].used = false;
        return 0;
    }
    return 0;
}

bool equal(const char* left, const char* right) {
    if (left == nullptr || right == nullptr) return left == right;
    while (*left != '\0' && *left == *right) {
        ++left;
        ++right;
    }
    return *left == *right;
}

i64 spawn_buffer_options(const char* name, const u8* bytes, u64 size, u32 argc,
                         const char* const* argv, const spawn_options& options) {
    (void)bytes; (void)argv; (void)options;
    ++kernel.spawn_calls;
    kernel.spawn_name = name;
    kernel.spawn_size = size;
    kernel.spawn_argc = argc;
    return kernel.spawn_result;
}
}

// The service reads /tone_worker.img through file::client and refuses to
// spawn bytes that do not match argv[2]. The real client needs a live files
// session, so the host test scripts the read instead.
namespace xos::file {
u8 worker_stub_image[audio::worker_image_limit];
u32 worker_stub_length = 0;
i64 worker_stub_result = 0;

bool client::init() { return true; }

i64 client::read_all(const char*, void* data, u32 capacity, u32& length) {
    length = 0;
    if (worker_stub_result != 0) { return worker_stub_result; }
    if (worker_stub_length > capacity) { return static_cast<i64>(status::no_space); }
    std::memcpy(data, worker_stub_image, worker_stub_length);
    length = worker_stub_length;
    return 0;
}
}

namespace {
int failures = 0;

void check(bool condition, const char* label) {
    std::printf("%-52s %s\n", label, condition ? "ok" : "FAIL");
    if (!condition) ++failures;
}

// A successful ipc_send (0) must not be treated as a transport failure.
void test_success_keeps_session() {
    reset_kernel();
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::capabilities)));
    handle_request(sessions[0], false);
    check(sessions[0].used, "capabilities: session survives a successful reply");
    check(kernel.close_calls == 0, "capabilities: endpoints stay open");
    check(kernel.poll_count == 0, "capabilities: no drain wait needed");
    check(reply_matches(0), "capabilities: reply queued with result 0");
}

// Closing revokes the mailbox, so the close reply must be read first.
void test_close_reply_drained() {
    reset_kernel();
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::close)));
    kernel.read_after_polls = 2;
    handle_request(sessions[0], false);
    check(reply_matches(0), "close: reply queued with result 0");
    check(kernel.poll_count == 2, "close: service waited until the peer read");
    check(!kernel.revoked_while_pending, "close: reply not revoked while queued");
    check(!sessions[0].used, "close: session closed after the drain");
}

// The overflow session replies "busy" and then closes: same drain requirement.
void test_overflow_busy_drained() {
    reset_kernel();
    overflow_session = sessions[0];
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::capabilities)));
    kernel.read_after_polls = 1;
    handle_request(overflow_session, true);
    check(reply_matches(xos::process_error_busy), "overflow: busy reply queued");
    check(kernel.poll_count == 1, "overflow: service waited until the peer read");
    check(!kernel.revoked_while_pending, "overflow: reply not revoked while queued");
    check(!overflow_session.used, "overflow: session closed after the drain");
}

// A peer that never reads must not hang the service loop.
void test_close_is_bounded() {
    reset_kernel();
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::close)));
    handle_request(sessions[0], false);
    check(!sessions[0].used, "stuck peer: session still closed");
    std::printf("stuck peer: polls=%u wait_ns=%llu\n", kernel.poll_count,
                static_cast<unsigned long long>(kernel.now_ns));
    check(kernel.poll_count >= 2 && kernel.poll_count <= 8,
          "stuck peer: bounded number of polls");
    // The service must give up within a handful of scheduler ticks.
    check(kernel.now_ns <= 8 * xos::thread_tick_ns, "stuck peer: bounded wall-clock wait");
}

// A dead peer (send error) is classified as a broken session, without waiting.
void test_send_failure_disconnects() {
    reset_kernel();
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::capabilities)));
    kernel.send_error = -7; // pipe_error_broken
    handle_request(sessions[0], false);
    check(!sessions[0].used, "broken peer: session disconnected");
    check(kernel.poll_count == 0, "broken peer: no drain wait");
    check(kernel.last_reply_size == 0, "broken peer: nothing queued");
}

// A full mailbox means the previous reply is unread: wait and retry once.
void test_full_mailbox_retries() {
    reset_kernel();
    script_request(make_request(static_cast<xos::u32>(xos::audio::operation::capabilities)));
    // An earlier reply is still queued on the service's send endpoint.
    kernel.endpoints[0].pending = true;
    kernel.read_after_polls = 1;
    handle_request(sessions[0], false);
    check(sessions[0].used, "full mailbox: session survives after the retry");
    check(kernel.poll_count == 1, "full mailbox: waited for the unread reply");
    check(reply_matches(0), "full mailbox: reply queued with result 0");
}

// argv[2] is a fixed 64-digit hex digest: anything else must be rejected
// rather than downgraded to "skip the check".
void test_digest_parser() {
    char text[65] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    xos::u8 out[32]{};
    check(parse_digest(text, out), "digest: 64 hex digits accepted");
    check(out[0] == 0x01 && out[1] == 0x23 && out[31] == 0xef, "digest: byte order big-endian");
    text[64] = '0';
    check(!parse_digest(text, out), "digest: trailing garbage rejected");
    text[64] = '\0';
    text[3] = 'z';
    check(!parse_digest(text, out), "digest: non-hex digit rejected");
    text[3] = '3';
    text[10] = '\0';
    check(!parse_digest(text, out), "digest: truncated value rejected");
    text[10] = 'a';
    check(!parse_digest(nullptr, out), "digest: null argument rejected");
}

// G-1/G-4: a note spawns only after the file bytes hash to the published
// digest, and the spawned process keeps the audio_tone name.
void test_worker_digest_gate() {
    reset_kernel();
    xos::file::worker_stub_result = 0;
    xos::file::worker_stub_length = 64;
    for (xos::u32 i = 0; i < xos::file::worker_stub_length; ++i) {
        xos::file::worker_stub_image[i] = static_cast<xos::u8>(i * 3 + 1);
    }
    sha256 hash;
    hash.update(xos::file::worker_stub_image, xos::file::worker_stub_length);
    hash.finish(expected_digest);
    digest_expected = true;

    xos::u64 child = 0;
    check(start_tone_worker(440, 100, child), "worker: matching digest spawns");
    check(kernel.spawn_calls == 1, "worker: exactly one spawn attempt");
    check(kernel.spawn_name != nullptr && std::strcmp(kernel.spawn_name, "audio_tone") == 0,
          "worker: process name stays audio_tone");
    check(kernel.spawn_size == xos::file::worker_stub_length,
          "worker: spawns the verified byte count");
    check(kernel.spawn_argc == 3, "worker: keeps the three worker arguments");
    check(child == 5001, "worker: child pid propagated");

    // Substituted file: same length, different bytes, no matching digest.
    xos::file::worker_stub_image[7] = static_cast<xos::u8>(xos::file::worker_stub_image[7] ^ 0xffu);
    child = 0;
    check(!start_tone_worker(440, 100, child), "worker: substituted image refused");
    check(kernel.spawn_calls == 1, "worker: no spawn after digest mismatch");
    check(child == 0, "worker: no child pid after mismatch");

    // An oversized or unreadable image refuses the same way.
    xos::file::worker_stub_result = static_cast<xos::i64>(xos::file::status::no_space);
    check(!start_tone_worker(440, 100, child), "worker: unreadable image refused");
    check(kernel.spawn_calls == 1, "worker: no spawn on read failure");
    xos::file::worker_stub_result = 0;
}
}

int main() {
    test_success_keeps_session();
    test_close_reply_drained();
    test_overflow_busy_drained();
    test_close_is_bounded();
    test_send_failure_disconnects();
    test_full_mailbox_retries();
    test_digest_parser();
    test_worker_digest_gate();
    if (failures != 0) {
        std::printf("audio_service_reply_test: %d failure(s)\n", failures);
        return 1;
    }
    std::printf("audio_service_reply_test: ok\n");
    return 0;
}
