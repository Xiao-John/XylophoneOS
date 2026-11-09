// SPDX-License-Identifier: Apache-2.0
// Host test for the audio SDK: every encoded request must satisfy the
// validation audio_service.cpp applies, and the transport must wait on the
// sys85 readiness path that named endpoints support (never sys81).
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <xos/audio_client.hpp>

namespace {
using namespace xos;
using namespace xos::audio;

constexpr u32 client_send_handle = 0x101;
constexpr u32 client_receive_handle = 0x102;
constexpr i64 send_retry_budget_full = 1;
constexpr i64 receive_never_ready = 1000000;

struct stub_state {
    u64 now_ns = 1000000000ull;
    u64 sleep_calls = 0;
    u64 sys_channel_calls = 0;  // sys81 wait: denied for named endpoints
    u64 ipc_wait_calls = 0;     // sys85 readiness: the compatible path
    u64 send_attempts = 0;
    i32 send_full_budget = 0;   // ipc_send reports full before succeeding
    i64 receive_ready_budget = 0;  // would_block replies left before ready
    i64 receive_wait_result = 0;   // override, e.g. pipe_error_broken
    u64 send_length = 0;
    u64 session_job = 0;
    u64 next_job = 5;
    std::vector<request> sent;
};
stub_state stub;

void reset_stub() { stub = stub_state{}; }

// Mirrors audio_service.cpp handle_request: the version/size/reserved header
// check first, then the per-operation field checks.
i64 service_rejects(const request& message) {
    if (message.version != protocol_version || message.size != sizeof(request) ||
        message.reserved != 0) {
        return process_error_invalid;
    }
    const auto op = static_cast<operation>(message.operation);
    auto notes_are_zero = [&](u32 first) {
        for (u32 i = first; i < max_notes; ++i) {
            if (message.notes[i].frequency_hz != 0 || message.notes[i].duration_ms != 0) {
                return false;
            }
        }
        return true;
    };
    if (op == operation::capabilities) {
        if (message.note_count != 0 || message.job_id != 0 || !notes_are_zero(0)) {
            return process_error_invalid;
        }
        return 0;
    }
    if (op == operation::submit) {
        if (validate_sequence(message.notes, message.note_count) != 0 || message.job_id != 0 ||
            !notes_are_zero(message.note_count)) {
            return process_error_invalid;
        }
        return 0;
    }
    if (op == operation::status || op == operation::cancel) {
        if (message.note_count != 0 || !notes_are_zero(0) || message.job_id == 0 ||
            message.job_id != stub.session_job) {
            return process_error_invalid;
        }
        return 0;
    }
    if (op == operation::close) {
        if (message.note_count != 0 || message.job_id != 0 || !notes_are_zero(0)) {
            return process_error_invalid;
        }
        return 0;
    }
    return process_error_invalid;
}

bool header_ok(const request& message, operation expected) {
    return message.version == protocol_version && message.size == sizeof(request) &&
           message.reserved == 0 && message.operation == static_cast<u32>(expected);
}
}  // namespace

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    using namespace xos;
    switch (number) {
    case sys_clock_monotonic:
        return static_cast<i64>(stub.now_ns);
    case sys_sleep_until:
        if (first > stub.now_ns) stub.now_ns = first;
        ++stub.sleep_calls;
        return 0;
    case sys_channel:  // sys81 wait branch denies non-generic_channel endpoints.
        ++stub.sys_channel_calls;
        return process_error_denied;
    case sys_ipc_wait: {
        ++stub.ipc_wait_calls;
        const u32 handle = static_cast<u32>(first);
        const auto mode = static_cast<ipc_wait_mode>(second);
        if (handle == client_send_handle) {
            return mode == ipc_wait_mode::try_send ? 0 : process_error_denied;
        }
        if (handle == client_receive_handle) {
            if (stub.receive_wait_result != 0) return stub.receive_wait_result;
            if (stub.receive_ready_budget > 0) {
                --stub.receive_ready_budget;
                return process_error_would_block;
            }
            return 0;
        }
        return process_error_denied;
    }
    case 4: {  // sdk::ipc_send
        ++stub.send_attempts;
        if (stub.send_full_budget > 0) {
            --stub.send_full_budget;
            return sdk::ipc_error_full;
        }
        request message{};
        std::memcpy(&message, reinterpret_cast<const void*>(second), sizeof(message));
        stub.send_length = third;
        stub.sent.push_back(message);
        return 0;
    }
    case 5: {  // sdk::ipc_recv
        const request& message = stub.sent.back();
        response reply{};
        reply.version = protocol_version;
        reply.size = sizeof(response);
        reply.state = static_cast<u32>(job_state::none);
        reply.max_notes = max_notes;
        reply.max_sequence_ms = max_sequence_ms;
        reply.min_frequency_hz = min_frequency_hz;
        reply.max_frequency_hz = max_frequency_hz;
        const auto op = static_cast<operation>(message.operation);
        if (op == operation::submit) {
            reply.job_id = stub.next_job++;
            stub.session_job = reply.job_id;
            reply.state = static_cast<u32>(job_state::accepted);
        } else if (op == operation::status || op == operation::cancel) {
            reply.job_id = stub.session_job;
            reply.state = static_cast<u32>(job_state::accepted);
        }
        reply.result = 0;
        std::memcpy(reinterpret_cast<void*>(second), &reply, sizeof(reply));
        return static_cast<i64>(sizeof(response));
    }
    case sys_ipc_endpoint:  // invalidate() closes both endpoints
        return 0;
    case sys_ipc_name: {
        if (first != static_cast<u64>(ipc_name_action::connect)) return process_error_denied;
        *reinterpret_cast<ipc_channel*>(third) = ipc_channel{client_send_handle,
                                                            client_receive_handle};
        return 0;
    }
    default:
        std::printf("unexpected syscall number %llu\n",
                    static_cast<unsigned long long>(number));
        std::abort();
    }
}
}  // namespace xos::sdk

namespace {
using namespace xos;

void test_request_header_matches_service_validation() {
    reset_stub();
    audio::client client;
    if (client.connect() != 0) { std::printf("FAIL connect\n"); std::exit(1); }
    if (stub.sent.size() != 1) { std::printf("FAIL capabilities send count\n"); std::exit(1); }
    const request& capabilities = stub.sent[0];
    if (!header_ok(capabilities, operation::capabilities)) {
        std::printf("FAIL capabilities header v=%u size=%u reserved=%llu\n", capabilities.version,
                    capabilities.size, static_cast<unsigned long long>(capabilities.reserved));
        std::exit(1);
    }
    if (service_rejects(capabilities) != 0) {
        std::printf("FAIL service rejects capabilities\n");
        std::exit(1);
    }
    if (stub.send_length != sizeof(request)) {
        std::printf("FAIL send length=%llu expected=%zu\n",
                    static_cast<unsigned long long>(stub.send_length), sizeof(request));
        std::exit(1);
    }
    // Reproduces the pre-fix encoding: zero-initialized request plus the
    // operation field only; the service predicate must reject it.
    request legacy{};
    legacy.operation = static_cast<u32>(operation::capabilities);
    if (service_rejects(legacy) != process_error_invalid) {
        std::printf("FAIL legacy zero header accepted\n");
        std::exit(1);
    }

    note notes[1] = {{440, 100}};
    u64 job = 0;
    if (client.submit(notes, 1, job) != 0 || job == 0) { std::printf("FAIL submit\n"); std::exit(1); }
    if (stub.sent.size() != 2 || !header_ok(stub.sent[1], operation::submit) ||
        service_rejects(stub.sent[1]) != 0 || stub.sent[1].note_count != 1 ||
        stub.sent[1].notes[0].frequency_hz != 440 || stub.sent[1].notes[0].duration_ms != 100) {
        std::printf("FAIL submit request\n");
        std::exit(1);
    }

    response out{};
    if (client.status(job, out) != 0) { std::printf("FAIL status\n"); std::exit(1); }
    if (stub.sent.size() != 3 || !header_ok(stub.sent[2], operation::status) ||
        service_rejects(stub.sent[2]) != 0) {
        std::printf("FAIL status request\n");
        std::exit(1);
    }
    if (client.cancel(job, out) != 0) { std::printf("FAIL cancel\n"); std::exit(1); }
    if (stub.sent.size() != 4 || !header_ok(stub.sent[3], operation::cancel) ||
        service_rejects(stub.sent[3]) != 0) {
        std::printf("FAIL cancel request\n");
        std::exit(1);
    }
    if (client.close() != 0) { std::printf("FAIL close\n"); std::exit(1); }
    if (stub.sent.size() != 5 || !header_ok(stub.sent[4], operation::close) ||
        service_rejects(stub.sent[4]) != 0) {
        std::printf("FAIL close request\n");
        std::exit(1);
    }
    if (stub.sys_channel_calls != 0 || stub.ipc_wait_calls == 0) {
        std::printf("FAIL wait path sys81=%llu sys85=%llu\n",
                    static_cast<unsigned long long>(stub.sys_channel_calls),
                    static_cast<unsigned long long>(stub.ipc_wait_calls));
        std::exit(1);
    }
    std::printf("header_ok=1 service_accepts_all=1 sys81_calls=0 sys85_calls=%llu\n",
                static_cast<unsigned long long>(stub.ipc_wait_calls));
}

void test_send_retries_when_endpoint_full() {
    reset_stub();
    stub.send_full_budget = send_retry_budget_full;
    audio::client client;
    if (client.connect() != 0) { std::printf("FAIL full-retry connect\n"); std::exit(1); }
    if (stub.send_attempts != 2 || stub.sent.size() != 1) {
        std::printf("FAIL full-retry attempts=%llu sent=%zu\n",
                    static_cast<unsigned long long>(stub.send_attempts), stub.sent.size());
        std::exit(1);
    }
    std::printf("send_full_retry=1 attempts=2\n");
}

void test_bounded_deadline_times_out() {
    reset_stub();
    stub.receive_ready_budget = receive_never_ready;
    const u64 start = stub.now_ns;
    audio::client client;
    const i64 result = client.connect();
    if (result != thread_error_timeout) {
        std::printf("FAIL deadline result=%lld\n", static_cast<long long>(result));
        std::exit(1);
    }
    if (client.connected()) { std::printf("FAIL deadline still connected\n"); std::exit(1); }
    if (stub.now_ns < start + 1000000000ull) {
        std::printf("FAIL deadline early now=%llu\n",
                    static_cast<unsigned long long>(stub.now_ns));
        std::exit(1);
    }
    if (stub.sleep_calls == 0) { std::printf("FAIL deadline no sleep\n"); std::exit(1); }
    std::printf("deadline_timeout=1 elapsed_ns=%llu\n",
                static_cast<unsigned long long>(stub.now_ns - start));
}

void test_disconnect_during_reply_wait() {
    reset_stub();
    stub.receive_wait_result = pipe_error_broken;
    audio::client client;
    const i64 result = client.connect();
    if (result != pipe_error_broken) {
        std::printf("FAIL disconnect result=%lld\n", static_cast<long long>(result));
        std::exit(1);
    }
    if (client.connected()) { std::printf("FAIL disconnect still connected\n"); std::exit(1); }
    std::printf("disconnect_broken=1\n");
}
}  // namespace

int main() {
    test_request_header_matches_service_validation();
    test_send_retries_when_endpoint_full();
    test_bounded_deadline_times_out();
    test_disconnect_during_reply_wait();
    std::printf("audio_client_host_test passed\n");
    return 0;
}
