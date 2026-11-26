// SPDX-License-Identifier: Apache-2.0
#include "files_slot_client.hpp"

namespace xos::user::pumpkin {
namespace storage = user::files_private_storage;

files_slot_client::~files_slot_client() {
    storage::close_pair(channel_);
}

bool files_slot_client::bind_bootstrap() {
    if (channel_.send != 0 || sdk::syscall(sys_process_stdio, 0, 0, 0) != 0) {
        return false;
    }
    storage::grant_reply offer;
    auto* bytes = reinterpret_cast<u8*>(&offer);
    usize offset = 0;
    const i64 deadline = storage::exchange_deadline();
    if (deadline < 0) {
        return false;
    }
    while (offset < sizeof(offer)) {
        const i64 received = sdk::read(0, bytes + offset, sizeof(offer) - offset);
        if (received > 0) {
            offset += static_cast<usize>(received);
        } else if (received != process_error_would_block || !storage::wait_tick(deadline)) {
            return false;
        }
    }
    if (offer.magic != storage::grant_magic || offer.version != storage::protocol_version ||
        offer.child != sdk::pid() || offer.status != storage::result::ok || offer.reserved != 0 ||
        !storage::peer_matches(offer.channel, offer.files)) {
        return false;
    }
    channel_ = offer.channel;
    return true;
}

bool files_slot_client::live() const {
    if (channel_.send == 0) {
        return false;
    }
    const i64 ready = sdk::ipc_wait(channel_.send, ipc_wait_mode::try_send);
    return ready == 0 || ready == process_error_would_block;
}

test_slot_io files_slot_client::io() {
    return {this,
            [](void* context, u32 slot, u8 (&bytes)[storage::slot_bytes]) {
                return static_cast<files_slot_client*>(context)->read(slot, bytes);
            },
            [](void* context, u32 slot, const u8 (&bytes)[storage::slot_bytes]) {
                return static_cast<files_slot_client*>(context)->write(slot, bytes);
            }};
}

bool files_slot_client::call(storage::request& request, storage::response& response) {
    const i64 deadline = storage::exchange_deadline();
    if (deadline < 0 || channel_.send == 0 || sequence_ == ~u64{0}) {
        return false;
    }
    request.sequence = ++sequence_;
    if (sdk::ipc_send(channel_.send, &request, sizeof(request)) != 0) {
        storage::close_pair(channel_);
        return false;
    }
    i64 received = 0;
    while ((received = sdk::ipc_recv(channel_.receive, &response, sizeof(response))) == process_error_would_block) {
        if (!storage::wait_tick(deadline)) {
            break;
        }
    }
    const u32 expected = request.op == storage::operation::read ? request.length : 0;
    if (received != sizeof(response) || response.version != storage::protocol_version ||
        response.op != request.op || response.sequence != request.sequence || response.status != storage::result::ok ||
        response.length != expected || has_bytes(response.data + expected, sizeof(response.data) - expected)) {
        storage::close_pair(channel_);
        return false;
    }
    return true;
}

bool files_slot_client::read(u32 slot, u8 (&bytes)[storage::slot_bytes]) {
    storage::request request;
    storage::response response;
    request.slot = slot;
    request.op = storage::operation::read;
    request.length = storage::payload_bytes;
    bool ok = true;
    for (u32 offset = 0; ok && offset < storage::slot_bytes; offset += storage::payload_bytes) {
        request.offset = offset;
        ok = call(request, response);
        if (ok) {
            __builtin_memcpy(bytes + offset, response.data, request.length);
        }
    }
    wipe_bytes(&response, sizeof(response));
    return ok;
}

bool files_slot_client::write(u32 slot, const u8 (&bytes)[storage::slot_bytes]) {
    storage::request request;
    storage::response response;
    request.slot = slot;
    request.op = storage::operation::begin;
    if (!call(request, response)) {
        return false;
    }
    request.op = storage::operation::chunk;
    request.length = storage::payload_bytes;
    bool ok = true;
    for (u32 offset = 0; ok && offset < storage::slot_bytes; offset += storage::payload_bytes) {
        request.offset = offset;
        __builtin_memcpy(request.data, bytes + offset, request.length);
        ok = call(request, response);
    }
    wipe_bytes(request.data, sizeof(request.data));
    request.op = storage::operation::commit;
    request.offset = request.length = 0;
    return ok && call(request, response);
}

}
