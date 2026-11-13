// SPDX-License-Identifier: Apache-2.0
#include <xos/ipc_v1.hpp>
#include <xos/thread_core.hpp>
#include <stdio.h>
using namespace xos;

namespace {
constexpr u32 sample_count = 120;
constexpr u32 payload_sizes[] = {0, 8, 64, 128, 256};
constexpr u64 label_base = 0x4950350000000000ull;
constexpr u64 reply_label_xor = 0xa55a5aa55aa55aa5ull;
struct server_context {
    u64 endpoint;
    u32 length;
    bool polling;
    i64 error;
    u8 payload[ipc_v1_max_message_bytes];
};

u8 byte_value(u32 sequence, u32 offset) {
    return static_cast<u8>((sequence * 37u + offset * 13u + 0x5du) & 0xffu);
}

void fail(const char* phase, i64 result = 0) {
    printf("[ipc-ip5] FAIL %s result=%lld\n", phase, static_cast<long long>(result));
}

bool valid_request(const server_context& context, u32 sequence, u64 label, u32 length) {
    if (label != (label_base | sequence) || length != context.length) { return false; }
    for (u32 i = 0; i < length; ++i) {
        if (context.payload[i] != byte_value(sequence, i)) { return false; }
    }
    return true;
}

bool first_receive(server_context& context, ipc_v1_receive& request, u32& sequence) {
    request = {};
    request.handle = context.endpoint;
    request.deadline_ns = context.polling ? ipc_v1_deadline_poll : ipc_v1_deadline_infinite;
    request.buffer = reinterpret_cast<u64>(context.payload);
    request.capacity = sizeof(context.payload);
    for (;;) {
        const i64 result = ipc_v1::receive(request);
        if (result == 0) {
            sequence = static_cast<u32>(request.label_out & 0xffffffffu);
            return true;
        }
        if (context.polling && result == static_cast<i64>(ipc_v1_error::would_block)) {
            (void)sdk::yield();
            request = {};
            request.handle = context.endpoint;
            request.deadline_ns = ipc_v1_deadline_poll;
            request.buffer = reinterpret_cast<u64>(context.payload);
            request.capacity = sizeof(context.payload);
            continue;
        }
        context.error = result;
        return false;
    }
}

u64 server(void* opaque) {
    auto& context = *static_cast<server_context*>(opaque);
    u32 sequence = 0;
    ipc_v1_receive received{};
    if (!first_receive(context, received, sequence)) { return 1; }
    for (u32 i = 0; i < sample_count + 1; ++i) {
        if (sequence != i || !valid_request(context, i, received.label_out, received.message_length_out)) {
            context.error = static_cast<i64>(ipc_v1_error::state);
            return 2;
        }
        const u64 reply_label = received.label_out ^ reply_label_xor;
        if (i + 1 == sample_count + 1) {
            ipc_v1_reply reply{};
            reply.reply_token = received.reply_token_out;
            reply.label = reply_label;
            reply.buffer = reinterpret_cast<u64>(context.payload);
            reply.length = context.length;
            context.error = ipc_v1::reply(reply);
            return context.error == 0 ? 0 : 3;
        }
        if (!context.polling) {
            ipc_v1_reply_receive next{};
            next.reply_token = received.reply_token_out;
            next.reply_label = reply_label;
            next.reply_buffer = reinterpret_cast<u64>(context.payload);
            next.reply_length = context.length;
            next.receive_capacity = sizeof(context.payload);
            next.receive_handle = context.endpoint;
            next.deadline_ns = ipc_v1_deadline_infinite;
            next.receive_buffer = reinterpret_cast<u64>(context.payload);
            context.error = ipc_v1::reply_receive(next);
            if (context.error != 0 || next.reply_consumed_out != 1) { return 4; }
            received.label_out = next.label_out;
            received.message_length_out = next.receive_length_out;
            received.reply_token_out = next.next_reply_token_out;
            sequence = static_cast<u32>(next.label_out & 0xffffffffu);
        } else {
            ipc_v1_reply reply{};
            reply.reply_token = received.reply_token_out;
            reply.label = reply_label;
            reply.buffer = reinterpret_cast<u64>(context.payload);
            reply.length = context.length;
            context.error = ipc_v1::reply(reply);
            if (context.error != 0) { return 5; }
            if (!first_receive(context, received, sequence)) { return 6; }
        }
    }
    return 7;
}

u64 percentile(const u64* values, u32 count, u32 percentile_value) {
    u64 sorted[sample_count]{};
    for (u32 i = 0; i < count; ++i) { sorted[i] = values[i]; }
    for (u32 i = 1; i < count; ++i) {
        const u64 item = sorted[i];
        u32 j = i;
        while (j != 0 && sorted[j - 1] > item) { sorted[j] = sorted[j - 1]; --j; }
        sorted[j] = item;
    }
    const u32 index = ((count - 1) * percentile_value + 99) / 100;
    return sorted[index];
}

bool run_case(u32 length, bool polling) {
    ipc_v1_feature_query baseline{};
    if (ipc_v1::query_features(baseline, true) != 0) { fail("switch-baseline"); return false; }
    u64 endpoint = 0;
    constexpr u32 rights = static_cast<u32>(ipc_v1_right::call) |
        static_cast<u32>(ipc_v1_right::receive) | static_cast<u32>(ipc_v1_right::manage);
    if (ipc_v1::endpoint_create(rights, endpoint) != 0 || endpoint == 0) {
        fail("endpoint-create"); return false;
    }
    server_context context{};
    context.endpoint = endpoint;
    context.length = length;
    context.polling = polling;
    u64 tid = 0;
    if (thread::create(tid, server, &context, thread_stack_min) != 0) {
        fail("server-create"); (void)ipc_v1::endpoint_close(endpoint); return false;
    }
    u64 samples[sample_count]{};
    u8 outgoing[ipc_v1_max_message_bytes]{};
    u8 incoming[ipc_v1_max_message_bytes]{};
    for (u32 sequence = 0; sequence < sample_count + 1; ++sequence) {
        for (u32 i = 0; i < length; ++i) { outgoing[i] = byte_value(sequence, i); }
        ipc_v1_call call{};
        call.handle = endpoint;
        call.deadline_ns = ipc_v1_deadline_infinite;
        call.label = label_base | sequence;
        call.send_buffer = reinterpret_cast<u64>(outgoing);
        call.reply_buffer = reinterpret_cast<u64>(incoming);
        call.send_length = length;
        call.reply_capacity = length;
        const u64 start = thread::clock();
        const i64 result = ipc_v1::call(call);
        const u64 finish = thread::clock();
        if (result != 0 || call.reply_length_out != length ||
            call.reply_label_out != (call.label ^ reply_label_xor)) {
            fail("call-result", result); return false;
        }
        for (u32 i = 0; i < length; ++i) {
            if (incoming[i] != outgoing[i]) { fail("reply-payload"); return false; }
        }
        if (sequence != 0) { samples[sequence - 1] = finish >= start ? finish - start : 0; }
    }
    u64 result = 0;
    if (thread::join(tid, result) != 0 || result != 0 || context.error != 0) {
        fail("server-join", context.error); (void)ipc_v1::endpoint_close(endpoint); return false;
    }
    if (ipc_v1::endpoint_close(endpoint) != 0) { fail("endpoint-close"); return false; }
    ipc_v1_feature_query observed{};
    if (ipc_v1::query_features(observed, true) != 0) { fail("switch-observation"); return false; }
    const u64 switches = observed.direct_switch_count - baseline.direct_switch_count;
    const bool eligible = !polling && length <= 64;
    if ((eligible && switches == 0) || (!eligible && switches != 0)) {
        fail("fastpath-observation", static_cast<i64>(switches)); return false;
    }
    printf("[ipc-ip5] mode=%s bytes=%u fastpath_eligible=%u switches=%llu samples=%u p50_ns=%llu p95_ns=%llu p99_ns=%llu\n",
        polling ? "poll-fallback" : "blocked-receiver", length,
        eligible ? 1u : 0u, static_cast<unsigned long long>(switches), sample_count,
        static_cast<unsigned long long>(percentile(samples, sample_count, 50)),
        static_cast<unsigned long long>(percentile(samples, sample_count, 95)),
        static_cast<unsigned long long>(percentile(samples, sample_count, 99)));
    return true;
}
}

int main() {
    if (thread::enable() != 0) { fail("thread-profile"); return 1; }
    ipc_v1_feature_query query{};
    if (ipc_v1::query_features(query) != 0 || (query.supported_features & 0x0f) != 0x0f) {
        fail("feature-mask", static_cast<i64>(query.supported_features)); return 1;
    }
    for (u32 length : payload_sizes) {
        if (!run_case(length, false) || !run_case(length, true)) { return 1; }
    }
    printf("[ipc-ip5] semantics-mask resource-close PASS\n");
    return 0;
}
