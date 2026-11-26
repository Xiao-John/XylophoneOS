// SPDX-License-Identifier: Apache-2.0
#include "files_private_broker.hpp"
#include <xos/file_abi.hpp>

namespace xos::user::files_private_storage {
namespace {

bool session_at(u32 index, file_session_info& session) {
    return sdk::syscall(sys_file_session, index, reinterpret_cast<u64>(&session)) == 0 &&
        session.pid != 0 && session.request_handle != 0 && session.response_handle != 0;
}

bool has_child(u64 controller, u64 child) {
    for (u32 index = 0; index < file::max_sessions; ++index) {
        file_session_info info;
        if (session_at(index, info) && info.pid == child && info.parent_pid == controller) {
            return true;
        }
    }
    return false;
}

void wipe(u8* bytes, usize length) {
    for (usize index = 0; index < length; ++index) {
        static_cast<volatile u8*>(bytes)[index] = 0;
    }
}

}

bool broker::establish_bootstrap() {
    return sdk::ipc_handles(bootstrap_.send, bootstrap_.receive) == 0 &&
        bootstrap_.send != 0 && bootstrap_.receive != 0;
}

bool broker::bootstrap_session(const file_session_info& client) const {
    return client.pid != 0 && bootstrap_.send != 0 && bootstrap_.receive != 0 &&
        client.request_handle == bootstrap_.receive && client.response_handle == bootstrap_.send;
}

bool broker::controller_alive() const {
    file_session_info source;
    return session_at(controller_index_, source) && source.pid == controller_ && bootstrap_session(source);
}

grant_reply broker::grant(const grant_request& request, const file_session_info& source,
                          u32 source_index, bool healthy) {
    grant_reply reply;
    reply.child = request.child;
    file_session_info current;
    if (!bootstrap_session(source) || !session_at(source_index, current) || current.pid != source.pid ||
        !bootstrap_session(current) || !healthy || request.magic != grant_magic ||
        request.version != protocol_version || request.reserved != 0 ||
        (request.rights != access::reader && request.rights != access::writer)) {
        return reply;
    }

    const auto clock = sdk::syscall(sys_clock_monotonic);
    if (clock < 0) {
        reply.status = result::io_error;
        return reply;
    }
    const auto now = static_cast<u64>(clock);
    if (lease_.occupied()) {
        (void)ready_for_request(now);
    }
    if (lease_.occupied()) {
        reply.status = result::busy;
        return reply;
    }
    if (!has_child(source.pid, request.child)) {
        reply.status = result::denied;
        return reply;
    }
    ipc_channel pair{};
    if (sdk::ipc_channel_create(request.child, pair) != 0 ||
        !peer_matches(pair, request.child) || !lease_.acquire(pair.send, request.rights)) {
        close_pair(pair);
        reply.status = result::io_error;
        return reply;
    }
    client_ = pair;
    controller_index_ = source_index;
    controller_ = source.pid;
    deadline_ = now + lease_ns;
    reply.files = sdk::pid();
    reply.channel = sdk::ipc_channel_for_peer(pair);
    reply.status = result::ok;
    return reply;
}

void broker::revoke() {
    lease_.release(client_.send);
    close_pair(client_);
    controller_ = 0;
    deadline_ = 0;
    reply_deadline_ = 0;
    wipe(reinterpret_cast<u8*>(&request_), sizeof(request_));
    wipe(reinterpret_cast<u8*>(&response_), sizeof(response_));
}

bool broker::ready_for_request(u64 now) {
    if (now >= deadline_ || !controller_alive()) {
        revoke();
        return false;
    }
    const i64 ready = sdk::ipc_wait(client_.send, ipc_wait_mode::try_send);
    if (ready == 0) {
        reply_deadline_ = 0;
        return true;
    }
    if (ready != process_error_would_block || reply_deadline_ == 0 || now >= reply_deadline_) {
        revoke();
    }
    return false;
}

void broker::poll(bool healthy) {
    if (!lease_.occupied()) {
        return;
    }
    const i64 clock = sdk::syscall(sys_clock_monotonic);
    if (!healthy || clock < 0) {
        revoke();
        return;
    }
    if (!ready_for_request(static_cast<u64>(clock))) {
        return;
    }
    const i64 received = sdk::ipc_recv(client_.receive, &request_, sizeof(request_));
    if (received == process_error_would_block) {
        return;
    }
    if (received != sizeof(request_) || !lease_.dispatch(client_.send, request_, response_) ||
        sdk::ipc_send(client_.send, &response_, sizeof(response_)) != 0) {
        revoke();
        return;
    }
    const i64 enqueued = sdk::syscall(sys_clock_monotonic);
    if (enqueued < clock) {
        revoke();
        return;
    }
    reply_deadline_ = static_cast<u64>(enqueued) + reply_ns;
    wipe(reinterpret_cast<u8*>(&request_), sizeof(request_));
    wipe(reinterpret_cast<u8*>(&response_), sizeof(response_));
}

}
