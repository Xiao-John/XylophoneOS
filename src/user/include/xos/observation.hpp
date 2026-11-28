// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/observation_service_abi.hpp>
#include <xos/process_abi.hpp>

namespace xos::observation {
// Capture is called only after the server authenticates and authorizes the peer.
// It may fill origin/object_id/generation/value; the server owns the envelope.
using capture_fn = status (*)(void*, kind, u64 deadline_ns, response&);
bool valid_response(const response& value);
const char* status_name(status value);
// Emit one bounded JSON observation with one record; no addresses or secrets.
status print_json(const response& value);

// Single-threaded owner. The owner serializes capture, authorization and revoke.
// This is an embeddable user-space endpoint, not a system-global inventory.
class server {
public:
    server() = default;
    server(const server&) = delete;
    server& operator=(const server&) = delete;
    ~server() { close(); }
    status initialize(capture_fn capture, void* context);
    status authorize(u64 peer_pid, u32 kinds, u32 reads, u64 expires_ns);
    status revoke(u64 peer_pid);
    // Owner-only retirement releases the grant slot and all that peer's channels.
    status forget(u64 peer_pid);
    // Takes ownership on success; authenticates BOTH directions via the kernel.
    status attach(ipc_channel channel);
    // At most one request per attached peer; never waits for an idle client.
    u32 poll();
    void close();
    u64 epoch() const { return epoch_; }
private:
    struct grant { u64 pid, image_generation, expires, revision; u32 kinds, remaining; bool revoked; };
    struct connection {
        ipc_channel channel;
        u64 peer, image_generation, next_sequence, grant_revision;
        bool pending;
        response reply;
    };
    grant grants_[max_clients]{};
    connection clients_[max_clients]{};
    u64 pid_ = 0, epoch_ = 0, next_observation_ = 1, next_grant_ = 1;
    capture_fn capture_ = nullptr;
    void* context_ = nullptr;
    void handle(connection&, const request&);
};

class client {
public:
    client() = default;
    client(const client&) = delete;
    client& operator=(const client&) = delete;
    ~client() { close(); }
    // PID and epoch must come from the caller's trusted supervisor/configuration.
    status connect(const char* name, u64 expected_pid, u64 expected_epoch);
    status read(kind subject, u64 deadline_ns, response& output,
                u64 expected_object = 0, u64 expected_generation = 0);
    void close();
private:
    ipc_channel channel_{};
    u64 pid_ = 0, epoch_ = 0, sequence_ = 1;
};
}
