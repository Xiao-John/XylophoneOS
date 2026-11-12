// SPDX-License-Identifier: Apache-2.0
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <xos/ipc_v1.hpp>
#include <xos/thread_core.hpp>

using namespace xos;

namespace {
constexpr u64 reply_xor = 0x9e3779b97f4a7c15ull;
constexpr u32 calls_per_client = 80;
constexpr u32 client_count = 2;
constexpr u32 calls_total = calls_per_client * client_count;
u64 rpc_endpoint;
volatile u32 failures;
volatile u32 server_reply_failures;
volatile u32 delayed_receiver_ready;

void fail(const char* label, i64 result = 0) {
    __atomic_add_fetch(&failures, 1u, __ATOMIC_RELAXED);
    printf("[ipc-v1] FAIL %s result=%lld\n", label, static_cast<long long>(result));
}

u64 request_id(u32 client, u32 sequence) {
    return (static_cast<u64>(client + 1) << 48) | sequence;
}

void* receiver(void*) {
    for (u32 i = 0; i < calls_total; ++i) {
        u64 payload = 0;
        ipc_v1_receive request{};
        request.handle = rpc_endpoint;
        request.deadline_ns = ipc_v1_deadline_infinite;
        request.buffer = reinterpret_cast<u64>(&payload);
        request.capacity = sizeof(payload);
        const i64 received = ipc_v1::receive(request);
        if (received != 0 || request.message_length_out != sizeof(payload) ||
            request.label_out != payload) {
            fail("rpc-receive", received); continue;
        }
        ipc_v1_reply reply{};
        reply.reply_token = request.reply_token_out;
        reply.label = request.label_out ^ reply_xor;
        reply.buffer = reinterpret_cast<u64>(&payload);
        reply.length = sizeof(payload);
        const i64 replied = ipc_v1::reply(reply);
        if (replied != 0) {
            __atomic_add_fetch(&server_reply_failures, 1u, __ATOMIC_RELAXED);
            fail("rpc-reply", replied);
        }
    }
    return nullptr;
}

struct client_arg { u32 client; };
void* caller(void* opaque) {
    const auto client = static_cast<client_arg*>(opaque)->client;
    for (u32 i = 0; i < calls_per_client; ++i) {
        const u64 value = request_id(client, i);
        u64 reply_payload = 0;
        ipc_v1_call request{};
        request.handle = rpc_endpoint;
        request.deadline_ns = ipc_v1_deadline_infinite;
        request.label = value;
        request.send_buffer = reinterpret_cast<u64>(&value);
        request.reply_buffer = reinterpret_cast<u64>(&reply_payload);
        request.send_length = sizeof(value);
        request.reply_capacity = sizeof(reply_payload);
        const i64 result = ipc_v1::call(request);
        if (result != 0 || request.phase_out != static_cast<u32>(ipc_v1_call_phase::replied) ||
            request.reply_length_out != sizeof(reply_payload) ||
            request.reply_label_out != (value ^ reply_xor) || reply_payload != value) {
            fail("rpc-call", result);
        }
    }
    return nullptr;
}

void* blocked_receiver(void* opaque) {
    auto* result = static_cast<i64*>(opaque);
    u8 payload[8]{};
    ipc_v1_receive request{};
    request.handle = rpc_endpoint;
    request.deadline_ns = ipc_v1_deadline_infinite;
    request.buffer = reinterpret_cast<u64>(payload);
    request.capacity = sizeof(payload);
    *result = ipc_v1::receive(request);
    return nullptr;
}

struct blocked_call_result { ipc_v1_call request; i64 result; };
void* blocked_caller(void* opaque) {
    auto* value = static_cast<blocked_call_result*>(opaque);
    u64 payload = 0;
    auto& request = value->request;
    request.handle = rpc_endpoint;
    request.deadline_ns = ipc_v1_deadline_infinite;
    request.reply_buffer = reinterpret_cast<u64>(&payload);
    request.reply_capacity = sizeof(payload);
    const u64 outgoing = 1;
    request.send_buffer = reinterpret_cast<u64>(&outgoing);
    request.send_length = sizeof(payload);
    value->result = ipc_v1::call(request);
    return nullptr;
}

struct notification_wait_result { u64 handle; i64 result; u64 bits; volatile u32 entered; };
bool create_endpoint(u32 rights, u64& handle);
void* notification_waiter(void* opaque) {
    auto* value = static_cast<notification_wait_result*>(opaque);
    __atomic_store_n(&value->entered, 1u, __ATOMIC_RELEASE);
    value->result = ipc_v1::notification_wait(value->handle, ipc_v1_deadline_infinite, value->bits);
    return nullptr;
}

u64 own_pid() {
    thread_info info{};
    return thread::info(info) == 0 ? info.pid : 0;
}

bool notifications_and_wait_sets() {
    const u64 pid = own_pid();
    if (pid == 0) { fail("process-pid"); return false; }
    constexpr u32 notification_rights = ipc_v1_notification_right_all;
    u64 notification = 0, bit_one = 0, bit_four = 0, zero_badge = 0;
    if (ipc_v1::notification_create(notification_rights, notification) != 0 ||
        ipc_v1::notification_delegate(notification, pid, 1, static_cast<u32>(ipc_v1_notification_right::signal), bit_one) != 0 ||
        ipc_v1::notification_delegate(notification, pid, 4, static_cast<u32>(ipc_v1_notification_right::signal), bit_four) != 0 ||
        ipc_v1::notification_delegate(notification, pid, 0, static_cast<u32>(ipc_v1_notification_right::signal), zero_badge) != 0) {
        fail("notification-delegate"); return false;
    }
    if (ipc_v1::notification_signal(bit_one) != 0 || ipc_v1::notification_signal(bit_four) != 0) {
        fail("notification-signal"); return false;
    }
    u64 bits = 0;
    if (ipc_v1::notification_wait(notification, 0, bits) != 0 || bits != 5) { fail("notification-or-merge"); }
    if (ipc_v1::notification_signal(zero_badge) != 0 ||
        ipc_v1::notification_wait(notification, 0, bits) != static_cast<i64>(ipc_v1_error::would_block) || bits != 0) {
        fail("notification-zero-badge");
    }
    notification_wait_result wait_result{notification, 0, 0, 0};
    pthread_t waiter{};
    if (pthread_create(&waiter, nullptr, notification_waiter, &wait_result) != 0) { fail("notification-wait-thread"); return false; }
    while (__atomic_load_n(&wait_result.entered, __ATOMIC_ACQUIRE) == 0) {
        (void)thread::sleep_until(thread::clock() + 1000000ull);
    }
    (void)thread::sleep_until(thread::clock() + 10000000ull);
    if (ipc_v1::notification_signal(bit_four) != 0 || pthread_join(waiter, nullptr) != 0 ||
        wait_result.result != 0 || wait_result.bits != 4) { fail("notification-block-wakeup", wait_result.result); }
    if (ipc_v1::notification_close(notification) != 0) { fail("notification-close"); return false; }

    u64 wait_set = 0, note_a = 0, note_b = 0, signal_a = 0, signal_b = 0;
    if (ipc_v1::wait_set_create(ipc_v1_wait_set_right_all, wait_set) != 0 ||
        ipc_v1::notification_create(notification_rights, note_a) != 0 ||
        ipc_v1::notification_create(notification_rights, note_b) != 0 ||
        ipc_v1::notification_delegate(note_a, pid, 2, static_cast<u32>(ipc_v1_notification_right::signal), signal_a) != 0 ||
        ipc_v1::notification_delegate(note_b, pid, 8, static_cast<u32>(ipc_v1_notification_right::signal), signal_b) != 0) {
        fail("wait-set-create"); return false;
    }
    ipc_v1_wait_set_add add_a{}; add_a.wait_set_handle = wait_set; add_a.source_handle = note_a;
    add_a.source_kind = static_cast<u32>(ipc_v1_wait_source::notification);
    ipc_v1_wait_set_add add_b{}; add_b.wait_set_handle = wait_set; add_b.source_handle = note_b;
    add_b.source_kind = static_cast<u32>(ipc_v1_wait_source::notification);
    if (ipc_v1::wait_set_add(add_a) != 0 || ipc_v1::wait_set_add(add_b) != 0 ||
        ipc_v1::notification_signal(signal_a) != 0 || ipc_v1::notification_signal(signal_b) != 0) {
        fail("wait-set-add-notification"); return false;
    }
    ipc_v1_wait_event events[2]{};
    ipc_v1_wait_set_wait wait{}; wait.handle = wait_set; wait.deadline_ns = 0;
    wait.events = reinterpret_cast<u64>(events); wait.capacity = 1;
    if (ipc_v1::wait_set_wait(wait) != static_cast<i64>(ipc_v1_error::buffer_too_small) || wait.count_out != 2) {
        fail("wait-set-capacity");
    }
    wait = {}; wait.handle = wait_set; wait.deadline_ns = 0;
    wait.events = reinterpret_cast<u64>(events); wait.capacity = 2;
    if (ipc_v1::wait_set_wait(wait) != 0 || wait.count_out != 2 ||
        events[0].kind != static_cast<u32>(ipc_v1_wait_event_kind::notification) ||
        events[1].kind != static_cast<u32>(ipc_v1_wait_event_kind::notification) ||
        events[0].value != 2 || events[1].value != 8) { fail("wait-set-notification-events"); }
    ipc_v1_wait_set_remove remove{}; remove.wait_set_handle = wait_set; remove.source_id = add_a.source_id_out;
    if (ipc_v1::wait_set_remove(remove) != 0) { fail("wait-set-remove-a"); }
    remove.source_id = add_b.source_id_out;
    if (ipc_v1::wait_set_remove(remove) != 0 || ipc_v1::notification_close(note_a) != 0 ||
        ipc_v1::notification_close(note_b) != 0 || ipc_v1::wait_set_close(wait_set) != 0) {
        fail("wait-set-notification-cleanup");
    }

    constexpr u32 endpoint_rights = static_cast<u32>(ipc_v1_right::call) |
        static_cast<u32>(ipc_v1_right::receive) | static_cast<u32>(ipc_v1_right::manage);
    u64 endpoint = 0; wait_set = 0;
    if (!create_endpoint(endpoint_rights, endpoint) ||
        ipc_v1::wait_set_create(ipc_v1_wait_set_right_all, wait_set) != 0) { fail("wait-set-endpoint-create"); return false; }
    ipc_v1_wait_set_add add_endpoint{}; add_endpoint.wait_set_handle = wait_set;
    add_endpoint.source_handle = endpoint;
    add_endpoint.source_kind = static_cast<u32>(ipc_v1_wait_source::endpoint);
    if (ipc_v1::wait_set_add(add_endpoint) != 0) { fail("wait-set-add-endpoint"); return false; }
    rpc_endpoint = endpoint;
    blocked_call_result queued{};
    pthread_t pending{};
    if (pthread_create(&pending, nullptr, blocked_caller, &queued) != 0) { fail("wait-set-call-thread"); return false; }
    wait = {}; wait.handle = wait_set; wait.deadline_ns = thread::clock() + 1000000000ull;
    wait.events = reinterpret_cast<u64>(events); wait.capacity = 2;
    if (ipc_v1::wait_set_wait(wait) != 0 || wait.count_out != 1 ||
        events[0].source_id != add_endpoint.source_id_out ||
        events[0].kind != static_cast<u32>(ipc_v1_wait_event_kind::endpoint_ready)) {
        fail("wait-set-endpoint-ready");
    }
    if (ipc_v1::endpoint_close(endpoint) != 0 || pthread_join(pending, nullptr) != 0 ||
        queued.result != static_cast<i64>(ipc_v1_error::closed)) { fail("wait-set-endpoint-close"); }
    wait = {}; wait.handle = wait_set; wait.deadline_ns = 0;
    wait.events = reinterpret_cast<u64>(events); wait.capacity = 2;
    if (ipc_v1::wait_set_wait(wait) != 0 || wait.count_out != 1 ||
        events[0].kind != static_cast<u32>(ipc_v1_wait_event_kind::closed)) { fail("wait-set-closed-event"); }
    remove = {}; remove.wait_set_handle = wait_set; remove.source_id = add_endpoint.source_id_out;
    if (ipc_v1::wait_set_remove(remove) != 0 || ipc_v1::wait_set_close(wait_set) != 0) {
        fail("wait-set-endpoint-cleanup");
    }
    return true;
}

void* delayed_receiver(void*) {
    __atomic_store_n(&delayed_receiver_ready, 1u, __ATOMIC_RELEASE);
    for (u32 i = 0; i < 12; ++i) {
        u64 payload = 0;
        ipc_v1_receive request{};
        request.handle = rpc_endpoint;
        request.deadline_ns = ipc_v1_deadline_infinite;
        request.buffer = reinterpret_cast<u64>(&payload);
        request.capacity = sizeof(payload);
        if (ipc_v1::receive(request) != 0) { fail("race-receive"); continue; }
        const u64 delay = (i & 1u) == 0 ? 20000000ull : 150000000ull;
        (void)thread::sleep_until(thread::clock() + delay);
        ipc_v1_reply reply{};
        reply.reply_token = request.reply_token_out;
        reply.label = request.label_out;
        reply.buffer = reinterpret_cast<u64>(&payload);
        reply.length = sizeof(payload);
        const i64 result = ipc_v1::reply(reply);
        if (result != 0 && result != static_cast<i64>(ipc_v1_error::stale_token)) {
            fail("race-reply", result);
        }
    }
    return nullptr;
}

bool create_endpoint(u32 rights, u64& handle) {
    const i64 result = ipc_v1::endpoint_create(rights, handle);
    if (result != 0 || handle == 0) { fail("endpoint-create", result); return false; }
    return true;
}

bool resource_recovery() {
    constexpr u32 manage = static_cast<u32>(ipc_v1_right::manage);
    for (u32 round = 0; round < 24; ++round) {
        u64 handles[ipc_v1_max_handles_per_process]{};
        for (u32 i = 0; i < ipc_v1_max_handles_per_process; ++i) {
            if (!create_endpoint(manage, handles[i])) { return false; }
        }
        u64 excess = 0;
        if (ipc_v1::endpoint_create(manage, excess) != static_cast<i64>(ipc_v1_error::resources) || excess != 0) {
            fail("handle-quota"); return false;
        }
        if (ipc_v1::endpoint_close(handles[0]) != 0) { fail("quota-close"); return false; }
        handles[0] = 0;
        if (!create_endpoint(manage, handles[0])) { fail("quota-recovery"); return false; }
        for (u64 handle : handles) {
            if (handle != 0 && ipc_v1::endpoint_close(handle) != 0) { fail("endpoint-close"); return false; }
        }
    }
    return true;
}

bool rpc_race_and_close() {
    constexpr u32 all_rights = static_cast<u32>(ipc_v1_right::call) |
        static_cast<u32>(ipc_v1_right::receive) | static_cast<u32>(ipc_v1_right::manage);
    if (!create_endpoint(all_rights, rpc_endpoint)) { return false; }
    pthread_t server{}, clients[client_count]{};
    client_arg args[client_count]{{0}, {1}};
    if (pthread_create(&server, nullptr, receiver, nullptr) != 0) { fail("server-thread"); return false; }
    for (u32 i = 0; i < client_count; ++i) {
        if (pthread_create(&clients[i], nullptr, caller, &args[i]) != 0) { fail("client-thread"); return false; }
    }
    for (auto& client : clients) { if (pthread_join(client, nullptr) != 0) { fail("client-join"); } }
    if (pthread_join(server, nullptr) != 0) { fail("server-join"); }
    if (ipc_v1::endpoint_close(rpc_endpoint) != 0) { fail("rpc-close"); return false; }

    if (!create_endpoint(all_rights, rpc_endpoint)) { return false; }
    pthread_t delayed{};
    __atomic_store_n(&delayed_receiver_ready, 0u, __ATOMIC_RELAXED);
    if (pthread_create(&delayed, nullptr, delayed_receiver, nullptr) != 0) { fail("delayed-thread"); return false; }
    while (__atomic_load_n(&delayed_receiver_ready, __ATOMIC_ACQUIRE) == 0) {
        (void)thread::sleep_until(thread::clock() + 1000000ull);
    }
    (void)thread::sleep_until(thread::clock() + 5000000ull);
    for (u32 i = 0; i < 12; ++i) {
        u64 reply_payload = 0;
        const u64 payload = i;
        ipc_v1_call request{};
        request.handle = rpc_endpoint; request.deadline_ns = thread::clock() + 100000000ull;
        request.label = payload; request.send_buffer = reinterpret_cast<u64>(&payload);
        request.reply_buffer = reinterpret_cast<u64>(&reply_payload);
        request.send_length = sizeof(payload); request.reply_capacity = sizeof(reply_payload);
        const i64 result = ipc_v1::call(request);
        if (result == 0) {
            if (request.phase_out != static_cast<u32>(ipc_v1_call_phase::replied) || reply_payload != payload) {
                fail("race-replied-state");
            }
        } else if (result == static_cast<i64>(ipc_v1_error::timeout)) {
            if (request.phase_out != static_cast<u32>(ipc_v1_call_phase::delivered)) { fail("race-timeout-phase"); }
        } else { fail("race-result", result); }
    }
    if (pthread_join(delayed, nullptr) != 0) { fail("delayed-join"); }
    if (ipc_v1::endpoint_close(rpc_endpoint) != 0) { fail("race-close"); return false; }

    if (!create_endpoint(all_rights, rpc_endpoint)) { return false; }
    i64 receive_result = 0;
    pthread_t receiver_thread{};
    if (pthread_create(&receiver_thread, nullptr, blocked_receiver, &receive_result) != 0) {
        fail("blocked-receiver-thread"); return false;
    }
    (void)thread::sleep_until(thread::clock() + 10000000ull);
    if (ipc_v1::endpoint_close(rpc_endpoint) != 0 || pthread_join(receiver_thread, nullptr) != 0 ||
        receive_result != static_cast<i64>(ipc_v1_error::closed)) { fail("close-wakes-receiver", receive_result); }

    if (!create_endpoint(all_rights, rpc_endpoint)) { return false; }
    blocked_call_result blocked{};
    pthread_t caller_thread{};
    if (pthread_create(&caller_thread, nullptr, blocked_caller, &blocked) != 0) {
        fail("blocked-caller-thread"); return false;
    }
    (void)thread::sleep_until(thread::clock() + 10000000ull);
    if (ipc_v1::endpoint_close(rpc_endpoint) != 0 || pthread_join(caller_thread, nullptr) != 0 ||
        blocked.result != static_cast<i64>(ipc_v1_error::closed) ||
        blocked.request.phase_out != static_cast<u32>(ipc_v1_call_phase::not_delivered)) {
        fail("close-cancels-call", blocked.result);
    }
    return true;
}
}

int main() {
    ipc_v1_feature_query query{};
    if (ipc_v1::query_features(query) != 0) {
        fail("feature-gate"); return 1;
    }
    (void)resource_recovery();
    (void)rpc_race_and_close();
    (void)notifications_and_wait_sets();
    thread_stats status{};
    if (sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&status)) != 0 ||
        status.threads != 1 || status.reserved != 0 || status.results != 0) { fail("thread-reclamation"); }
    if (__atomic_load_n(&failures, __ATOMIC_RELAXED) != 0 ||
        __atomic_load_n(&server_reply_failures, __ATOMIC_RELAXED) != 0) {
        printf("[ipc-v1] race-resource failures=%u server-reply=%u\n",
               static_cast<unsigned>(failures), static_cast<unsigned>(server_reply_failures));
        return 1;
    }
    printf("[ipc-v1] race-resource rpc-race close-wakeup handle-quota-recovery repeated=24 PASS\n");
    return 0;
}
