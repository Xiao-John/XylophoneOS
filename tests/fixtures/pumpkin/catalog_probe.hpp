// SPDX-License-Identifier: Apache-2.0
// Included by the existing trusted registrar fixture. Every state mutation
// crosses the production daemon transport; the catalog itself is explicit test
// provisioning and is not evidence of signed repository verification.
u8 catalog_failure = 0;
u32 catalog_received_bytes = 0;

bool catalog_channel_budget(const daemon& server) {
    if (!server.pid || !server.backing_channels.transmit || !server.backing_channels.receive ||
        server.backing_channels.transmit == server.backing_channels.receive) {
        catalog_failure = 14; return false;
    }
    u32 owned = 0;
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const auto result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) break;
        if (result || info.version != channel_version || info.size != sizeof(info)) {
            catalog_failure = 14; return false;
        }
        if (info.controller_pid == sdk::pid()) ++owned;
    }
    // Enumeration excludes channels where this PID is owner but neither peer.
    // The two successful backing create calls are recorded above; both peers
    // independently authenticate their owner and opposite peer with find_pair.
    // No legacy control pair may additionally be visible to this supervisor.
    if (owned != 0) { catalog_failure = 15; return false; }
    return true;
}
u64 catalog_deadline() {
    const auto now = sdk::syscall(sys_clock_monotonic);
    return now < 0 ? 0 : static_cast<u64>(now) + dynamic::startup_deadline_limit_ns;
}
catalog::authority catalog_binding(daemon& server) {
    catalog::authority result{catalog::authority_version, sizeof(catalog::authority), server.pid, {}, {}};
    __builtin_memcpy(result.realm, anchored_installation_realm.bytes, sizeof(result.realm));
    static_assert(sizeof(disk_test_service) <= sizeof(result.service));
    __builtin_memcpy(result.service, disk_test_service, sizeof(disk_test_service));
    return result;
}
bool catalog_snapshot(daemon& server, provisioning_reply& reply) {
    provisioning_request request{}; request.operation = provisioning_operation::checkpoint;
    const bool ok = provisioning_expect(server.control, request, reply, status::ok);
    if (!ok) catalog_failure = 2;
    return ok;
}
bool catalog_seed(daemon& server) {
    provisioning_reply reply{};
    if (!catalog_snapshot(server, reply)) return false;
    provisioning_request request{};
    request.operation = provisioning_operation::stage_catalog; request.expected = reply.current;
    request.candidate.catalog = pumpkin_catalog_fixture;
    auto& checkpoint = request.candidate.checkpoint;
    checkpoint.repository_id[0] = 7; checkpoint.key_epoch = 1; checkpoint.sequence = 1;
    checkpoint.trusted_unix_seconds = 100; checkpoint.metadata_sha256[0] = 8;
    const bool ok = provisioning_expect(server.control, request, reply, status::ok);
    if (!ok) catalog_failure = 3;
    return ok;
}
bool catalog_install(daemon& server, u32 active, u32 revoked) {
    provisioning_reply reply{};
    if (!catalog_snapshot(server, reply)) return false;
    const auto& selected = reply.candidate.catalog;
    if (selected.count != 2 || selected.active != active || selected.revoked != revoked) {
        catalog_failure = 4; return false;
    }
    for (u32 i = 0; i < 2; ++i) {
        if (selected.roots[i] != pumpkin_catalog_fixture.roots[i]) { catalog_failure = 5; return false; }
    }
    const auto result = dynamic::install_anchored(catalog_binding(server), catalog_deadline());
    if (result != dynamic::error::none) { catalog_failure = static_cast<u8>(40 + static_cast<u32>(result)); return false; }
    return true;
}
i64 catalog_child(u32 index, const char* operation = "leaf", const char* expectation = nullptr,
                  u32 input = 0, u32 output = 0) {
    sdk::spawn_options options{};
    for (auto& fd : options.stdio) fd = -2;
    if (input) options.stdio[0] = input;
    if (output) options.stdio[1] = output;
    options.delegate_spawn_depth = 3;
    options.prepare_child = [](u64 child, void*) {
        return sdk::syscall(sys_process_authority, child, static_cast<u64>(process_authority_mode::copy_from_caller));
    };
    const char* arguments[]{pumpkin_catalog_main_paths[index], operation, expectation};
    execution::launch_diagnostic diagnostic{};
    execution::image_receipt receipt{};
    const auto child = execution::spawn_file_diagnosed_receipt(arguments[0], expectation ? 3u : 2u, arguments,
                                                               options, diagnostic, receipt);
    if (child <= 0) {
        // Preserve stage and small native error in the bounded PKA1 finish byte:
        // 100 + stage*10 + min(abs(error),9). This does not turn a failure into PASS.
        const u32 code = child < 0 && child > -10 ? static_cast<u32>(-child) : 9u;
        catalog_failure = static_cast<u8>(100u + static_cast<u32>(diagnostic.stage) * 10u + code);
    }
    return child;
}
bool catalog_wait(i64 child) {
    if (child <= 0) return false;
    process_status state{};
    if (sdk::wait_flags(static_cast<u64>(child), state) || state.outcome != process_outcome::exited) {
        catalog_failure = 180; return false;
    }
    if (state.code) { catalog_failure = static_cast<u8>(state.code < 64 ? 181 + state.code : 244); return false; }
    return true;
}
bool catalog_leaf(daemon& server, u32 active, u32 revoked) {
    return catalog_channel_budget(server) && catalog_install(server, active, revoked) &&
        catalog_wait(catalog_child(active)) && catalog_channel_budget(server);
}
bool catalog_switch(daemon& server, status expected) {
    provisioning_reply reply{};
    if (!catalog_snapshot(server, reply)) return false;
    provisioning_request request{};
    request.operation = provisioning_operation::activate_generation;
    request.expected = reply.current; request.app.application = 1;
    if (!provisioning_expect(server.control, request, reply, expected)) { catalog_failure = 6; return false; }
    return expected == status::outcome_unknown || catalog_leaf(server, expected == status::ok ? 1u : 0u, 0);
}
bool catalog_pipe_bytes(u32 handle, char expected, u32 count) {
    catalog_received_bytes = 0;
    const auto started = sdk::syscall(sys_clock_monotonic);
    if (started < 0) return false;
    const auto end = static_cast<u64>(started) + 60'000'000'000;
    while (count) {
        char value = 0;
        const auto result = sdk::syscall(sys_pipe_read, handle, reinterpret_cast<u64>(&value), 1);
        if (result == 1) { if (value != expected) return false; --count; ++catalog_received_bytes; continue; }
        if (result != process_error_would_block) return false;
        // Reexec requests arrive at the parent's real launch-control endpoint.
        if (launch::poll() < 0) return false;
        const auto now = sdk::syscall(sys_clock_monotonic);
        if (now < 0 || static_cast<u64>(now) >= end ||
            sdk::syscall(sys_sleep_until, static_cast<u64>(now) + 1'000'000)) return false;
    }
    return true;
}
bool catalog_descendants(daemon& server, bool unavailable) {
    if (!catalog_channel_budget(server) || !catalog_install(server, 0, 0)) return false;
    pipe_handles input{}, output{};
    if (sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&input)) ||
        sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&output))) { catalog_failure = 7; return false; }
    const auto child = catalog_child(0, "reexec", unavailable ? "unavailable" : "deny",
                                     input.read_token, output.write_token);
    close_pipe(input.read_token); close_pipe(output.write_token);
    bool ready = child > 0 && catalog_pipe_bytes(output.read_token, 'R', 3);
    if (!ready && !catalog_failure) {
        process_status ended{};
        const auto waited = sdk::wait_flags(static_cast<u64>(child), ended, process_wait_nonblocking);
        if (waited == 0 && ended.outcome == process_outcome::exited) {
            catalog_failure = static_cast<u8>(ended.code < 64 ? 181 + ended.code : 244);
        } else {
            // Distinguish the number of actual ready descendants from a child
            // exit. This is diagnostic only; every code remains a failure.
            catalog_failure = static_cast<u8>(20 + catalog_received_bytes);
        }
    }
    if (ready && unavailable) {
        ready = server.stop();
    } else if (ready) {
        provisioning_reply reply{};
        ready = catalog_snapshot(server, reply);
        provisioning_request request{};
        request.operation = provisioning_operation::revoke_generation;
        request.expected = reply.current; request.app.application = 0;
        ready = ready && provisioning_expect(server.control, request, reply, status::ok);
    }
    if (!ready && !catalog_failure) catalog_failure = 9;
    ready = ready && write_pipe(input.write_token, "GGG", 3) && catalog_pipe_bytes(output.read_token, 'D', 3);
    if (!ready && !catalog_failure) catalog_failure = 10;
    close_pipe(input.write_token); close_pipe(output.read_token);
    return ready && catalog_wait(child);
}
bool catalog_owner_admission(daemon& server) {
    provisioning_reply reply{};
    if (!catalog_snapshot(server, reply)) return false;
    const auto& selected = reply.candidate.catalog;
    if (selected.count != 2 || selected.revoked & 2u) { catalog_failure = 11; return false; }
    launch::artifact owner{}, target{};
    owner.id = selected.roots[0].generation; target.id = selected.roots[1].generation;
    __builtin_memcpy(owner.sha256, selected.roots[0].manifest_sha256, sizeof(owner.sha256));
    __builtin_memcpy(target.sha256, selected.roots[1].manifest_sha256, sizeof(target.sha256));
    if (dynamic::restore_authority(catalog_binding(server), owner) != dynamic::error::none) {
        catalog_failure = 12; return false;
    }
    const auto result = dynamic::authority_admission({}, target, catalog_deadline());
    if (result != ((selected.revoked & 1u) ? process_error_denied : 0)) { catalog_failure = 13; return false; }
    return true;
}
bool catalog_revoke_last(daemon& server) {
    provisioning_reply reply{};
    if (!catalog_snapshot(server, reply) || reply.candidate.catalog.revoked != 1) return false;
    provisioning_request request{};
    request.operation = provisioning_operation::revoke_generation;
    request.expected = reply.current; request.app.application = 1;
    return provisioning_expect(server.control, request, reply, status::ok);
}
bool catalog_all_revoked(daemon& server) {
    provisioning_reply reply{};
    return catalog_snapshot(server, reply) && reply.candidate.catalog.revoked == 3 &&
        dynamic::install_anchored(catalog_binding(server), catalog_deadline()) != dynamic::error::none &&
        !dynamic::configured();
}
