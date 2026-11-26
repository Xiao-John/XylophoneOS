// SPDX-License-Identifier: Apache-2.0
#include "resource_broker.hpp"

namespace {
using namespace xos;
using namespace xos::user::pumpkin;

struct channel_owner {
    ipc_channel value{};
    ~channel_owner() { close_ipc(value); }
};

struct client_slot {
    ipc_channel pair{};
    u64 number = 0;
    u64 expires = 0;
    bool replied = false;
};

wire_status transport_status(status result) {
    switch (result) {
    case status::ok: return wire_status::ok;
    case status::denied: return wire_status::denied;
    case status::io_error: return wire_status::io_error;
    default: return wire_status::unavailable;
    }
}

bool process_read(client_slot& client, sealed_blob& object, broker_authority& authority, u64 now) {
    if (now >= client.expires) { return false; }
    if (client.replied) {
        return sdk::ipc_wait(client.pair.send, ipc_wait_mode::try_send) == process_error_would_block;
    }
    broker_read input{};
    const auto count = sdk::ipc_recv(client.pair.receive, &input, sizeof(input));
    if (count == process_error_would_block) { return true; }
    const u64 peer = authenticated_peer(client.pair);
    if (count != sizeof(input) || input.version != wire_version || input.reserved ||
        !peer || input.ticket.scope == nonce{} || !input.ticket.number) { return false; }
    const auto received = monotonic_now();
    if (received < 0 || static_cast<u64>(received) < now) { return false; }
    now = static_cast<u64>(received);
    if (now >= client.expires) { return false; }
    const auto client_deadline = input.deadline < client.expires ? input.deadline : client.expires;
    broker_data output{};
    if (input.deadline > now && input.deadline - now <= max_request_ns) {
        struct read_context {
            broker_authority& authority;
            const ipc_channel& pair;
            broker_read_request message;
        } call{authority, client.pair, {wire_version, 0, 0, client_deadline, peer, client.number, input.ticket}};
        const blob_read_check check{&call, [](void* context, const nonce& incarnation, const owner_record& owner) {
            auto& read = *static_cast<read_context*>(context);
            read.message.incarnation = incarnation;
            read.message.object = owner.object;
            read.message.owner = owner.owner;
            const auto allowed = read.authority.authorize(read.message);
            if (allowed != status::ok) { return allowed; }
            return read.authority.live() && authenticated_peer(read.pair) == read.message.peer
                ? status::ok : status::denied;
        }};
        output.result = transport_status(object.read_associated(input.object, check, output.data));
    }
    const auto before_reply = monotonic_now();
    if (before_reply < 0 || static_cast<u64>(before_reply) < now ||
        static_cast<u64>(before_reply) >= client_deadline ||
        !authority.live() || authenticated_peer(client.pair) != peer ||
        sdk::ipc_send(client.pair.send, &output, sizeof(output)) != 0) { return false; }
    const auto sent = monotonic_now();
    if (sent < before_reply) { return false; }
    client.expires = static_cast<u64>(sent) + reply_budget_ns;
    client.replied = true;
    return true;
}

int serve(sealed_blob& object, broker_authority& authority, const ipc_channel& control, u64 parent) {
    if (sdk::ipc_name_publish(broker_service_name) != 0) { return 13; }
    client_slot clients[4]{};
    u64 next_connection = 0;
    int result = 0;
    while (authority.live() && authenticated_peer(control) == parent) {
        const auto clock = monotonic_now();
        if (clock < 0) { result = 13; break; }
        const auto now = static_cast<u64>(clock);
        for (auto& client : clients) {
            if (client.number && !process_read(client, object, authority, now)) {
                close_ipc(client.pair);
                client = {};
            }
        }
        ipc_channel incoming{};
        const auto accepted = sdk::ipc_name_try_accept(incoming);
        if (accepted == 0) {
            client_slot* free = nullptr;
            for (auto& client : clients) {
                if (!client.number) { free = &client; break; }
            }
            if (free && next_connection != ~u64{0} && authenticated_peer(incoming)) {
                const broker_opened opened{wire_version, 0, ++next_connection};
                if (sdk::ipc_send(incoming.send, &opened, sizeof(opened)) == 0) {
                    *free = {incoming, opened.connection, now + max_request_ns, false};
                    incoming = {};
                }
            }
            close_ipc(incoming);
        } else if (accepted != process_error_would_block) {
            result = 13;
            break;
        }
        if (!sleep_tick(now)) { result = 13; break; }
    }
    (void)sdk::ipc_name_unpublish(broker_service_name);
    for (auto& client : clients) { close_ipc(client.pair); }
    return result;
}
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (startup == nullptr || startup->magic != startup_magic || startup->argc != 2) { return 10; }
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    channel_owner control;
    if (sdk::ipc_channel_create(0, control.value) != 0) { return 11; }
    const auto parent = authenticated_peer(control.value);
    const auto now = monotonic_now();
    if (!parent || now < 0) { return 11; }
    {
        channel_owner rendezvous;
        const control_message offer{wire_version, 0, sdk::ipc_channel_for_peer(control.value), {}};
        if (sdk::ipc_name_connect(args[1], rendezvous.value) != 0 ||
            authenticated_peer(rendezvous.value) != parent ||
            sdk::ipc_send(rendezvous.value.send, &offer, sizeof(offer)) != 0) { return 11; }
        broker_configuration config{};
        const u64 deadline = static_cast<u64>(now) + max_request_ns;
        if (!receive_broker_frame(control.value, config, deadline) || config.version != wire_version ||
            !config.daemon || !config.owner.number || config.owner.realm == nonce{} ||
            config.incarnation == nonce{} || config.length == 0 || config.length > sealed_blob_capacity) { return 11; }
        // The parent's reply witnesses consumption of the rendezvous offer.
        close_ipc(rendezvous.value);

        file::client files;
        sealed_blob object{files};
        nonce registry{};
        if (sdk::syscall(sys_random_bytes, reinterpret_cast<u64>(registry.bytes), sizeof(registry.bytes)) != 0 ||
            !files.init() || object.publish({registry, broker_object_number, 1}, config.incarnation, config.owner,
                config.bytes, config.length) != status::ok) { return 12; }
        ipc_channel daemon_pair{};
        broker_authority authority;
        if (sdk::ipc_channel_create(config.daemon, daemon_pair) != 0 ||
            !authority.bind(daemon_pair, config.daemon)) { return 12; }
        const auto remote = sdk::ipc_channel_for_peer(daemon_pair);
        const broker_ready ready{wire_version, 0, {sdk::pid(), remote.send, remote.receive}};
        if (sdk::ipc_send(control.value.send, &ready, sizeof(ready)) != 0) { return 12; }
        return serve(object, authority, control.value, parent);
    }
}
