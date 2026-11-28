// SPDX-License-Identifier: Apache-2.0
#include "provisioning_protocol.hpp"

namespace xos::user::pumpkin {
namespace {
template<typename type> bool zero(const type& value) {
    return !has_bytes(reinterpret_cast<const u8*>(&value), sizeof(value));
}
status invoke(provisioning_store& store, service_core& core, const connection_id& connection,
              provisioning_role role, const provisioning_request& request, u64 now,
              const entropy_api& entropy, provisioning_reply& reply, publisher_admission admission) {
    const auto op = request.operation;
    const auto& app = request.app;
    if (app.reserved || app.name_length > name_limit || app.data_length > application_data_bytes ||
        has_bytes(reinterpret_cast<const u8*>(app.name) + app.name_length, name_limit - app.name_length) ||
        has_bytes(app.data + app.data_length, application_data_bytes - app.data_length)) { return status::invalid; }
    if (op != provisioning_operation::stage_catalog && !zero(request.candidate)) { return status::invalid; }
    if (op != provisioning_operation::delegate_publisher && !zero(request.publisher)) { return status::invalid; }
    if (op == provisioning_operation::checkpoint) {
        if (!zero(app) || !zero(request.session) || !zero(request.expected)) { return status::invalid; }
        return store.checkpoint(reply.candidate.checkpoint, reply.candidate.catalog);
    }
    if (op == provisioning_operation::read_application || op == provisioning_operation::write_application) {
        if (role != provisioning_role::client || !zero(app.owner) || app.name_length || app.rights || !zero(request.expected)) {
            return status::denied;
        }
        identity_id owner{};
        const session_id session{request.session.scope, request.session.number};
        auto result = core.session_identity(connection, now, session, owner);
        if (result != status::ok) { return result; }
        u64 epoch = 0;
        result = store.authorize_application(owner, app.application, app.key, epoch);
        if (result != status::ok) { return result; }
        if (app.authorization_epoch != epoch) { return status::denied; }
        if (op == provisioning_operation::read_application) {
            if (app.data_revision || app.installation_generation || has_bytes(app.installation_sha256, 32) || app.data_length) {
                return status::invalid;
            }
            return store.read_application(owner, app.application, epoch, reply.app);
        }
        return store.write_application(owner, app.application, epoch, app.data_revision, app.data, app.data_length,
                                       app.installation_generation, app.installation_sha256);
    }
    if (!zero(request.session) || (role != provisioning_role::registrar &&
        !(role == provisioning_role::catalog_publisher &&
          (op == provisioning_operation::stage_catalog || op == provisioning_operation::admit_generation)))) {
        return status::denied;
    }
    switch (op) {
    case provisioning_operation::create_application:
        if (!zero(request.expected) || app.application || app.authorization_epoch || app.data_revision ||
            !zero(app.key) || app.installation_generation || has_bytes(app.installation_sha256, 32) || app.data_length) {
            return status::invalid;
        }
        return store.create_application(app.owner, {app.name, app.name_length}, app.rights, entropy, reply.app, reply.key);
    case provisioning_operation::revoke_application: {
        auto canonical = application_input{};
        canonical.application = app.application; canonical.authorization_epoch = app.authorization_epoch;
        if (!zero(request.expected) || __builtin_memcmp(&canonical, &app, sizeof(app))) { return status::invalid; }
        return store.revoke_application(app.application, app.authorization_epoch);
    }
    case provisioning_operation::stage_catalog:
        if (!zero(app)) { return status::invalid; }
        return store.stage_catalog(request.expected, request.candidate);
    case provisioning_operation::install_application: {
        if (!zero(request.expected) || !zero(app.owner) || app.name_length || app.rights || !zero(app.key)) {
            return status::invalid;
        }
        return store.install_application(app.application, app.authorization_epoch, app.data_revision,
            app.data, app.data_length, app.installation_generation, app.installation_sha256);
    }
    case provisioning_operation::delegate_publisher:
        if (!zero(app) || !zero(request.expected) || !admission.delegate) { return status::invalid; }
        return admission.delegate(admission.context, request.publisher);
    case provisioning_operation::inspect_application: {
        auto canonical = application_input{}; canonical.application = app.application;
        if (!zero(request.expected) || __builtin_memcmp(&canonical, &app, sizeof(app))) { return status::invalid; }
        return store.inspect_application(app.application, reply.app);
    }
    case provisioning_operation::revoke_generation:
    case provisioning_operation::admit_generation: {
        auto canonical = application_input{}; canonical.application = app.application;
        if (__builtin_memcmp(&canonical, &app, sizeof(app)) || app.application >= catalog_root_limit) { return status::invalid; }
        if (op == provisioning_operation::revoke_generation) {
            return store.revoke_generation(request.expected, static_cast<u32>(app.application));
        }
        if (request.expected != store.version()) { return status::conflict; }
        const auto result = store.checkpoint(reply.candidate.checkpoint, reply.candidate.catalog);
        if (result != status::ok) { return result; }
        return app.application < reply.candidate.catalog.count &&
            !(reply.candidate.catalog.revoked & (1u << app.application)) ? status::ok : status::denied;
    }
    default: return status::invalid;
    }
}
}
bool dispatch_provisioning(provisioning_store& store, service_core& core, const connection_id& connection,
                           provisioning_role role, u64& last_sequence, const provisioning_request& request,
                           u64 now, const entropy_api& entropy, provisioning_reply& reply, publisher_admission admission) {
    reply = {};
    if (request.magic != provisioning_magic || request.version != provisioning_protocol_version || request.reserved ||
        !request.sequence || request.sequence != last_sequence + 1 || request.deadline <= now ||
        request.deadline - now > max_request_ns || request.operation < provisioning_operation::checkpoint ||
        request.operation > provisioning_operation::install_application) { return false; }
    last_sequence = request.sequence;
    reply.operation = request.operation; reply.sequence = request.sequence;
    reply.result = invoke(store, core, connection, role, request, now, entropy, reply, admission);
    reply.current = store.version();
    if (!store.live()) { core.stop(); }
    // No ordinary API exposes a password or application verifier.
    wipe_bytes(reply.app.verifier, sizeof(reply.app.verifier));
    return true;
}
}
