// SPDX-License-Identifier: Apache-2.0
#include "native_ipc.hpp"
#if XOS_PUMPKIN_NATIVE_LOGIN
#include "login_resource.hpp"
#endif
#if XOS_PUMPKIN_RESOURCE_BRIDGE
#include "resource_bridge.hpp"
#endif
#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
#include "named_resource_rpc.hpp"
#endif
#if XOS_PUMPKIN_PROVISIONING_STORE
#include "provisioning_protocol.hpp"
#endif

namespace xos::user::pumpkin {


namespace {

struct transport_session {
    ipc_channel channel{};
    connection_id connection;
    u64 sequence = 0;
    u64 expires = 0;
    u64 reply_expires = 0;
    bool catalog_publisher = false;
};

void disconnect(service_core& core, transport_session& session) {
    core.detach(session.connection);
    close_ipc(session.channel);
    session = {};
}

bool attach(service_core& core, transport_session& session, ipc_channel channel, admission_role role, u64 now) {
    connection_id connection;
    if (core.attach(role, now, connection) != status::ok) {
        close_ipc(channel);
        return false;
    }
    session = {channel, connection, 0, now + connection_lifetime_ns, 0};
    return true;
}

enum class progress { keep, drop, failure };

progress process_request(service_core& core, transport_session& session, u64& now, bool draining,
                         [[maybe_unused]] login_resource* resource = nullptr,
                         [[maybe_unused]] resource_bridge* bridge = nullptr,
                         [[maybe_unused]] named_resource_store* named = nullptr,
                         [[maybe_unused]] bool registrar = false,
                         [[maybe_unused]] provisioning_store* provisioning = nullptr,
                         [[maybe_unused]] const entropy_api& entropy = {},
                         [[maybe_unused]] transport_session* clients = nullptr) {
    if (now >= session.expires) {
        return progress::drop;
    }
    const auto send_ready = sdk::ipc_wait(session.channel.send, ipc_wait_mode::try_send);
    if (send_ready != 0) {
        const bool awaiting_consumption = send_ready == process_error_would_block &&
            (session.reply_expires == 0 || now < session.reply_expires);
        return awaiting_consumption ? progress::keep : progress::drop;
    }
    session.reply_expires = 0;
    if (draining) {
        return progress::drop;
    }

    wire_request request{};
#if XOS_PUMPKIN_PROVISIONING_STORE
    alignas(8) u8 incoming[sizeof(provisioning_request)]{};
    const auto received = sdk::ipc_recv(session.channel.receive, incoming, sizeof(incoming));
    if (received == sizeof(request)) { __builtin_memcpy(&request, incoming, sizeof(request)); }
#else
    const auto received = sdk::ipc_recv(session.channel.receive, &request, sizeof(request));
#endif
    if (received == process_error_would_block) {
        return progress::keep;
    }
    wire_reply reply;
    const auto received_at = monotonic_now();
    const bool clock_ok = received_at >= 0 && static_cast<u64>(received_at) >= now;
    if (clock_ok) {
        now = static_cast<u64>(received_at);
    }
#if XOS_PUMPKIN_PROVISIONING_STORE
    if (received == sizeof(provisioning_request)) {
        provisioning_request operation{};
        __builtin_memcpy(&operation, incoming, sizeof(operation));
        wipe_bytes(incoming, sizeof(incoming));
        provisioning_reply result{};
        const publisher_admission admission{clients, [](void* context, const publisher_binding& binding) {
            if (!context || !binding.peer || !binding.send || !binding.receive || binding.send == binding.receive) {
                return status::invalid;
            }
            const ipc_channel proposed{binding.send, binding.receive};
            if (authenticated_peer(proposed) != binding.peer) { return status::denied; }
            auto* sessions = static_cast<transport_session*>(context);
            for (u32 i = 0; i < client_limit; ++i) {
                auto& target = sessions[i];
                if (target.channel.send == binding.send && target.channel.receive == binding.receive) {
                    if (target.catalog_publisher) { return status::conflict; }
                    target.catalog_publisher = true;
                    return status::ok;
                }
            }
            return status::not_found;
        }};
        const bool sent = provisioning && clock_ok && now < session.expires &&
            dispatch_provisioning(*provisioning, core, session.connection,
                registrar ? provisioning_role::registrar : session.catalog_publisher ?
                    provisioning_role::catalog_publisher : provisioning_role::client,
                session.sequence, operation, now, entropy, result, admission) &&
            sdk::ipc_send(session.channel.send, &result, sizeof(result)) == 0;
        wipe_bytes(&operation, sizeof(operation)); wipe_bytes(&result, sizeof(result));
        if (!clock_ok) { return progress::failure; }
        if (!sent) { return progress::drop; }
        const auto enqueued_at = monotonic_now();
        if (enqueued_at < 0 || static_cast<u64>(enqueued_at) < now) { return progress::failure; }
        now = static_cast<u64>(enqueued_at); session.reply_expires = now + reply_budget_ns;
        return progress::keep;
    }
    wipe_bytes(incoming, sizeof(incoming));
#endif
    const wire_extension* extension = nullptr;
#if XOS_PUMPKIN_NATIVE_LOGIN
    struct resource_context { login_resource* resource; ipc_channel channel; bool registrar; };
    resource_context ingress{resource, session.channel, registrar};
    const wire_extension login_extension{&ingress,
        [](void* context, service_core& state, const connection_id& connection,
           const wire_request& incoming, u64 at, wire_reply& outgoing) {
            auto& input = *static_cast<resource_context*>(context);
            return input.resource->invoke(state, connection, input.channel, input.registrar, incoming, at, outgoing);
        }};
    if (resource != nullptr) { extension = &login_extension; }
#endif
#if XOS_PUMPKIN_RESOURCE_BRIDGE
    struct bridge_context { resource_bridge* bridge; ipc_channel channel; bool registrar; };
    bridge_context broker{bridge, session.channel, registrar};
    const wire_extension resource_extension{&broker,
        [](void* context, service_core& state, const connection_id& connection,
           const wire_request& incoming, u64 at, wire_reply& outgoing) {
            auto& input = *static_cast<bridge_context*>(context);
            return input.bridge->invoke(state, connection, input.channel, input.registrar, incoming, at, outgoing);
        }, wire_operation::admit_resource_broker, wire_operation::begin_resource_read};
    if (bridge != nullptr && (extension == nullptr || request.operation >= resource_extension.first)) {
        extension = &resource_extension;
    }
#endif
#if XOS_PUMPKIN_NAMED_RESOURCE_STORE
    struct named_context { named_resource_store* store; bool registrar; bool broker_only; };
    named_context names{named, registrar, bridge != nullptr};
    const wire_extension named_extension{&names,
        [](void* context, service_core& state, const connection_id& connection,
           const wire_request& incoming, u64 at, wire_reply& outgoing) {
            auto& input = *static_cast<named_context*>(context);
            if (input.broker_only && incoming.operation == wire_operation::read_named_resource) { return status::denied; }
            return invoke_named_resource(*input.store, state, connection, input.registrar, incoming, at, outgoing);
        }, wire_operation::put_named_resource, wire_operation::put_named_binary};
    if (named != nullptr && request.operation >= named_extension.first) { extension = &named_extension; }
#endif
    // The kernel copies the single-slot packet. Never retry after dispatch,
    // since the mutation may already have executed.
    const bool sent = received == sizeof(request) && clock_ok && now < session.expires &&
        dispatch_request(core, session.connection, session.sequence, request, now, reply, extension) &&
        sdk::ipc_send(session.channel.send, &reply, sizeof(reply)) == 0;
    wipe_bytes(&request, sizeof(request));
    wipe_bytes(&reply, sizeof(reply));
    if (!clock_ok) {
        return progress::failure;
    }
    if (!sent) {
        return progress::drop;
    }
    const auto enqueued_at = monotonic_now();
    if (enqueued_at < 0 || static_cast<u64>(enqueued_at) < now) {
        return progress::failure;
    }
    now = static_cast<u64>(enqueued_at);
    session.reply_expires = now + reply_budget_ns;
    return progress::keep;
}

}

int serve_native(const store_api& store, const nonce& realm, const entropy_api& entropy,
                 ipc_channel control, u64 controller, const char* service_name,
                 backing_liveness backing, login_resource* resource, resource_bridge* bridge,
                 named_resource_store* named, provisioning_store* provisioning) {
    service_core core;
    transport_session registrar, clients[client_limit]{};
    const i64 initial = monotonic_now();
    if (controller == 0 || authenticated_peer(control) != controller || initial < 0 ||
        core.start(store, realm, entropy) != status::ok) {
        close_ipc(control);
        return 11;
    }
    if (!attach(core, registrar, control, admission_role::registrar, static_cast<u64>(initial))) {
        return 11;
    }
    if (sdk::ipc_name_publish(service_name) != 0) {
        disconnect(core, registrar);
        return 11;
    }

    bool draining = false;
    int exit_code = 0;
    while (registrar.channel.send != 0) {
        const i64 clock = monotonic_now();
        if (clock < 0) {
            exit_code = 12;
            break;
        }
        if (!draining && backing.live != nullptr && !backing.live(backing.context)) {
            // A durable mutation may have queued outcome_unknown. Preserve its
            // bounded reply drain while admitting no further operations.
            core.stop();
            draining = true;
            exit_code = 12;
        }
        auto now = static_cast<u64>(clock);
        if (core.expire(now) != status::ok) {
            draining = true;
            exit_code = 12;
        }
        const auto control_result = process_request(core, registrar, now, draining, resource, bridge, named, true,
                                                    provisioning, entropy, clients);
        if (control_result != progress::keep) {
            if (control_result == progress::failure) {
                exit_code = 12;
            }
            break;
        }
        // A registrar mutation can stop the core. Drain its queued reply
        // while refusing any additional client work and admissions.
        if (!draining && core.expire(now) != status::ok) {
            draining = true;
            exit_code = 12;
        }
        for (auto& client : clients) {
            if (client.channel.send == 0) {
                continue;
            }
            const auto result = process_request(core, client, now, draining, resource, bridge, named, false,
                                                provisioning, entropy);
            if (result != progress::keep) {
                disconnect(core, client);
            }
            if (result == progress::failure) {
                draining = true;
                exit_code = 12;
            }
        }
#if XOS_PUMPKIN_RESOURCE_BRIDGE
        if (bridge != nullptr) {
            if (draining) { bridge->close(); }
            else { bridge->poll(core, now); }
        }
#endif
        if (!draining) {
            for (u32 count = 0; count != 4; ++count) {
                ipc_channel incoming{};
                const auto accepted = sdk::ipc_name_try_accept(incoming);
                if (accepted == process_error_would_block) {
                    break;
                }
                if (accepted != 0) {
                    draining = true;
                    exit_code = 12;
                    break;
                }
                transport_session* free_session = nullptr;
                for (auto& client : clients) {
                    if (client.channel.send == 0) {
                        free_session = &client;
                        break;
                    }
                }
                if (free_session == nullptr || authenticated_peer(incoming) == 0) {
                    close_ipc(incoming);
                    continue;
                }
                (void)attach(core, *free_session, incoming, admission_role::client, now);
            }
        }
        if (!sleep_tick(now)) {
            exit_code = 12;
            break;
        }
    }

    (void)sdk::ipc_name_unpublish(service_name);
    disconnect(core, registrar);
    for (auto& client : clients) {
        disconnect(core, client);
    }
    core.stop();
    return exit_code;
}

}
