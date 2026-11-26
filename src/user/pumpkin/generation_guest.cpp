// SPDX-License-Identifier: Apache-2.0
#include "generation_guest.hpp"
#include "native_ipc.hpp"

namespace xos::user::pumpkin::anchor_guest {

bool client::bind_bootstrap() {
    ipc_channel parent{};
    if (sdk::ipc_channel_create(0, parent) != 0) {
        return false;
    }
    controller_ = authenticated_peer(parent);
    close_ipc(parent);
    if (controller_ == 0) {
        return false;
    }

    auto* bytes = reinterpret_cast<u8*>(&proxy_);
    usize received = 0;
    const u64 end = deadline();
    while (received < sizeof(proxy_)) {
        const i64 count = sdk::read(0, bytes + received, sizeof(proxy_) - received);
        if (count > 0) {
            received += static_cast<usize>(count);
        } else {
            const i64 now = monotonic_now();
            if (count != process_error_would_block || now < 0 ||
                static_cast<u64>(now) >= end || !sleep_tick(static_cast<u64>(now))) {
                return false;
            }
        }
    }
    return proxy_ != 0 && find_pair(controller_, proxy_, channel_);
}

bool client::live() const {
    pair found{};
    return channel_.transmit != 0 && find_pair(controller_, proxy_, found) &&
        found.transmit == channel_.transmit && found.receive == channel_.receive;
}

bool client::call(packet& message, packet& reply) {
    if (!live() || sequence_ == ~u64{0}) {
        return false;
    }
    message.sequence = ++sequence_;
    const u64 end = deadline();
    const bool valid = end != 0 &&
        sdk::channel_send_wait(channel_.transmit, &message, sizeof(message), end) == 0 &&
        sdk::channel_receive_wait(channel_.receive, &reply, sizeof(reply), end) == sizeof(reply) &&
        header(reply, message.op, message.sequence) && reply.expected == generation_mark{};
    if (!valid) {
        (void)sdk::channel_close(channel_.transmit);
        (void)sdk::channel_close(channel_.receive);
        channel_ = {};
    }
    return valid;
}

generation_record_io client::io() {
    return {
        this,
        [](void* context, generation_mark& record) {
            packet message{}, reply{};
            message.op = operation::read;
            if (!static_cast<client*>(context)->call(message, reply) ||
                reply.result > static_cast<u8>(load_result::io_error)) {
                return load_result::io_error;
            }
            if (reply.result == static_cast<u8>(load_result::loaded)) {
                record = reply.value;
            } else if (reply.value != generation_mark{}) {
                return load_result::io_error;
            }
            return static_cast<load_result>(reply.result);
        },
        [](void* context, const generation_mark& expected, const generation_mark& next) {
            packet message{}, reply{};
            message.op = operation::publish;
            message.expected = expected;
            message.value = next;
            if (!static_cast<client*>(context)->call(message, reply) ||
                reply.value != generation_mark{} || reply.result > static_cast<u8>(replace_result::outcome_unknown)) {
                return replace_result::outcome_unknown;
            }
            return static_cast<replace_result>(reply.result);
        },
    };
}

}
