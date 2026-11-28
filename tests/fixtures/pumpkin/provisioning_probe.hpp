// SPDX-License-Identifier: Apache-2.0
// Included inside the existing trusted anchored supervisor fixture. All state
// mutations below cross the production daemon's authenticated IPC transport.
bool provisioning_expect(ipc_client& client, provisioning_request& request, provisioning_reply& reply, status expected) {
    return client.call(request, reply) == exchange::received && reply.result == expected;
}

bool provisioning_inspect(daemon& server, u64 application, application_record& out) {
    provisioning_request request{}; provisioning_reply reply{};
    request.operation = provisioning_operation::inspect_application; request.app.application = application;
    if (!provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    out = reply.app; return !has_bytes(out.verifier, sizeof(out.verifier));
}

bool provisioning_recovered(daemon& server, bool updated) {
    application_record app{}, revoked{};
    if (!provisioning_inspect(server, 1, app) || !provisioning_inspect(server, 2, revoked) ||
        app.data_length != 3 || app.data_revision != (updated ? 3u : 2u) ||
        app.installation_generation != (updated ? 2u : 1u) || app.installation_sha256[0] != (updated ? 2u : 1u) ||
        __builtin_memcmp(app.data, updated ? "new" : "old", 3) || !app.enabled || revoked.enabled) { return false; }
    provisioning_request request{}; provisioning_reply reply{};
    request.operation = provisioning_operation::checkpoint;
    return provisioning_expect(server.control, request, reply, status::ok) &&
        reply.candidate.catalog.count == 2 && reply.candidate.catalog.active == 0 &&
        reply.candidate.catalog.epoch == 1 && reply.candidate.checkpoint.sequence == 1;
}

bool provisioning_cycle(daemon& server) {
    test_account owner;
    if (!enroll(server, owner)) { return false; }
    provisioning_request request{}; provisioning_reply reply{};
    request.operation = provisioning_operation::create_application;
    request.app.owner = {owner.identity.scope, owner.identity.number}; request.app.rights = 3;
    request.app.name_length = 6; __builtin_memcpy(request.app.name, "editor", 6);
    if (!provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    const auto first = reply.app; credential first_key = reply.key;
    __builtin_memcpy(request.app.name, "viewer", 6);
    if (!provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    const auto second = reply.app; credential second_key = reply.key;
    ipc_client user, descendant;
    wire_reply login_reply{};
    if (!bind_ordinary(user, server.pid) || !login(user, owner.key, login_reply, wire_status::ok)) { return false; }
    const auto user_session = login_reply.token;
    if (!bind_ordinary(descendant, server.pid) || !login(descendant, owner.key, login_reply, wire_status::ok)) { return false; }
    const auto descendant_session = login_reply.token;
    request = {}; request.operation = provisioning_operation::read_application;
    request.session = user_session; request.app.application = first.number;
    request.app.authorization_epoch = first.authorization_epoch; request.app.key = first_key;
    if (!provisioning_expect(user, request, reply, status::ok)) { return false; }
    request.app.application = second.number; request.app.authorization_epoch = second.authorization_epoch;
    if (!provisioning_expect(user, request, reply, status::denied)) { return false; }
    request.app.key = second_key;
    if (!provisioning_expect(user, request, reply, status::ok)) { return false; }
    request.session = descendant_session;
    if (!provisioning_expect(descendant, request, reply, status::ok)) { return false; }
    request = {}; request.operation = provisioning_operation::checkpoint;
    if (!provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    request = {}; request.operation = provisioning_operation::stage_catalog; request.expected = reply.current;
    auto& candidate = request.candidate;
    candidate.catalog.count = 2; candidate.catalog.epoch = 1; candidate.catalog.sdk_sha256[0] = 1;
    candidate.catalog.roots[0].generation = 1; candidate.catalog.roots[0].manifest_sha256[0] = 1;
    candidate.catalog.roots[1].generation = 2; candidate.catalog.roots[1].manifest_sha256[0] = 2;
    constexpr char first_manifest[] = "/generation/1/manifest", second_manifest[] = "/generation/2/manifest";
    __builtin_memcpy(candidate.catalog.roots[0].manifest, first_manifest, sizeof(first_manifest));
    __builtin_memcpy(candidate.catalog.roots[1].manifest, second_manifest, sizeof(second_manifest));
    candidate.checkpoint.repository_id[0] = 1; candidate.checkpoint.key_epoch = 1;
    candidate.checkpoint.sequence = 1; candidate.checkpoint.trusted_unix_seconds = 100;
    candidate.checkpoint.metadata_sha256[0] = 1;
    if (!provisioning_expect(user, request, reply, status::denied) ||
        !provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    request = {}; request.operation = provisioning_operation::write_application;
    request.session = user_session; request.app.application = first.number;
    request.app.authorization_epoch = first.authorization_epoch; request.app.data_revision = 1;
    request.app.key = first_key; request.app.installation_generation = 1; request.app.installation_sha256[0] = 1;
    request.app.data_length = 3; __builtin_memcpy(request.app.data, "old", 3);
    if (!provisioning_expect(user, request, reply, status::ok)) { return false; }
    request = {}; request.operation = provisioning_operation::revoke_application;
    request.app.application = second.number; request.app.authorization_epoch = second.authorization_epoch;
    if (!provisioning_expect(server.control, request, reply, status::ok)) { return false; }
    request = {}; request.operation = provisioning_operation::read_application;
    request.session = user_session; request.app.application = second.number;
    request.app.authorization_epoch = second.authorization_epoch; request.app.key = second_key;
    if (!provisioning_expect(user, request, reply, status::denied)) { return false; }
    request.session = descendant_session;
    const bool denied = provisioning_expect(descendant, request, reply, status::denied);
    wipe_bytes(&first_key, sizeof(first_key)); wipe_bytes(&second_key, sizeof(second_key));
    wipe_bytes(&request, sizeof(request)); wipe_bytes(&reply, sizeof(reply));
    return denied && provisioning_recovered(server, false);
}

bool provisioning_update(daemon& server, status expected) {
    application_record app{};
    if (!provisioning_inspect(server, 1, app)) { return false; }
    provisioning_request request{}; provisioning_reply reply{};
    request.operation = provisioning_operation::install_application;
    request.app.application = 1; request.app.authorization_epoch = app.authorization_epoch;
    request.app.data_revision = app.data_revision; request.app.installation_generation = 2;
    request.app.installation_sha256[0] = 2; request.app.data_length = 3;
    __builtin_memcpy(request.app.data, "new", 3);
    if (!provisioning_expect(server.control, request, reply, expected)) { return false; }
    return expected == status::outcome_unknown || provisioning_recovered(server, expected == status::ok);
}
