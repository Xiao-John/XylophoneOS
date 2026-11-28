// SPDX-License-Identifier: Apache-2.0
// Included inside the anchored registrar fixture. Publication and admission
// use the production daemon, native loader and Files transports.
u8 distribution_failure = 2;

struct distribution_logs {
    file::client files{};
    u32 handles[2]{};
    bool open(const char* output, const char* errors, sdk::spawn_options& options) {
        u32 size = 0, version = 0;
        if (!files.init() || !files.set_deadline(storage::exchange_deadline())) return false;
        const char* paths[]{output, errors};
        for (u32 i = 0; i < 2; ++i) {
            if (files.open(paths[i], file::write_only | file::open_create | file::open_truncate,
                           handles[i], size, version)) { (void)close(); return false; }
            options.file_handles[i + 1] = handles[i];
            options.open_flags[i + 1] = 1; // POSIX O_WRONLY in GNU startup.
        }
        return true;
    }
    bool close() {
        // Closing inherited logging references is a new bounded Files
        // operation after spawn. Do not reuse the pre-spawn open deadline,
        // and never retry an unconfirmed close.
        if (!files.set_deadline(storage::exchange_deadline())) return false;
        bool accepted = true;
        for (auto& handle : handles) {
            if (handle) {
                const auto result = files.close(handle);
                accepted = accepted && result == 0;
                if (!result) handle = 0;
            }
        }
        return accepted;
    }
};

bool distribution_receive(ipc_channel channel, xypm_distribution::publisher_startup& message, u64 deadline) {
    for (;;) {
        const auto received = sdk::ipc_recv(channel.receive, &message, sizeof(message));
        if (received != process_error_would_block)
            return received == sizeof(message) && message.magic == xypm_distribution::publisher_startup_magic &&
                !message.reserved;
        if (!storage::wait_tick(deadline)) return false;
    }
}

bool distribution_run(daemon& server, const char* repository, const char* lock, int code,
                      bool interrupted = false, bool delegate = true) {
    using namespace xypm_distribution;
    static distribution_logs logs;
    static u32 ordinal = 0;
    constexpr char parent_name[] = "xypm-p1d-parent";
    char output[] = "/dist/run_0.out", errors[] = "/dist/run_0.err";
    if (ordinal >= 10) { distribution_failure = 9; return false; }
    output[10] = errors[10] = static_cast<char>('0' + ordinal++);
    if (sdk::ipc_name_publish(parent_name)) { distribution_failure = 10; return false; }
    const char* executable = interrupted ? "/usr/bin/xypm-fault" : "/usr/bin/xypm";
    const char* arguments[]{executable, "repo-install-generation", repository, lock, "--controller", parent_name};
    const char* environment[]{"XYP_DISTRIBUTION_STOP_AFTER=1"};
    sdk::spawn_options options{};
    options.prepare_child = [](u64 child, void*) {
        return sdk::syscall(sys_process_authority, child, static_cast<u64>(process_authority_mode::copy_from_caller));
    };
    if (interrupted) { options.environment = environment; options.environment_count = 1; }
    if (!logs.open(output, errors, options)) {
        (void)sdk::ipc_name_unpublish(parent_name); distribution_failure = 11; return false;
    }
    const auto child = sdk::spawn_file_options(executable, 6, arguments, options);
    const bool logs_closed = logs.close();
    if (child <= 0 || !logs_closed) {
        if (child > 0) { (void)sdk::syscall(10, static_cast<u64>(child)); process_status ignored{}; (void)sdk::wait(child, ignored); }
        (void)sdk::ipc_name_unpublish(parent_name);
        distribution_failure = child <= 0 ? static_cast<u8>(16 + (-child & 31)) : 12; return false;
    }
    ipc_channel discovery{}, parental{};
    const auto deadline = storage::exchange_deadline();
    bool accepted = false;
    for (;;) {
        const auto result = sdk::ipc_name_try_accept(discovery);
        if (!result) {
            if (authenticated_peer(discovery) == static_cast<u64>(child)) { accepted = true; break; }
            close_ipc(discovery);
        } else if (result != process_error_would_block) break;
        if (!storage::wait_tick(deadline)) break;
    }
    (void)sdk::ipc_name_unpublish(parent_name);
    bool connected = accepted;
    if (!connected) distribution_failure = 48;
    publisher_startup offer{};
    if (connected) {
        connected = distribution_receive(discovery, offer, deadline) && offer.phase == publisher_phase::offer &&
            authenticated_peer(offer.channel) == static_cast<u64>(child);
        if (!connected) distribution_failure = 49;
        else parental = offer.channel;
    }
    if (connected) {
        publisher_startup welcome{}; welcome.phase = publisher_phase::broker; welcome.broker_pid = server.pid;
        static_assert(sizeof(disk_test_service) <= sizeof(welcome.broker_name));
        __builtin_memcpy(welcome.broker_name, disk_test_service, sizeof(disk_test_service));
        connected = sdk::ipc_send(parental.send, &welcome, sizeof(welcome)) == 0;
        if (!connected) distribution_failure = 50;
    }
    close_ipc(discovery);
    publisher_startup ready{};
    if (connected) {
        connected = distribution_receive(parental, ready, storage::exchange_deadline()) &&
            ready.phase == publisher_phase::connected;
        if (!connected) distribution_failure = 51;
    }
    if (connected && delegate) {
        provisioning_request request{}; provisioning_reply reply{};
        request.operation = provisioning_operation::delegate_publisher;
        request.publisher = {static_cast<u64>(child), ready.channel.send, ready.channel.receive};
        connected = provisioning_expect(server.control, request, reply, status::ok);
        if (!connected) distribution_failure = 52;
    }
    if (connected) {
        publisher_startup granted{}; granted.phase = publisher_phase::delegated;
        connected = sdk::ipc_send(parental.send, &granted, sizeof(granted)) == 0;
        if (!connected) distribution_failure = 53;
    }
    // Retain the pair until the child has consumed its ACK. Closing an endpoint
    // immediately after send would invalidate the still unread final message.
    if (!connected) (void)sdk::syscall(10, static_cast<u64>(child));
    process_status result{};
    const auto waited = sdk::wait(static_cast<u64>(child), result);
    close_ipc(parental);
    if (!connected) return false;
    if (waited) { distribution_failure = 54; return false; }
    if (result.outcome != process_outcome::exited) { distribution_failure = 55; return false; }
    if (result.code != code) { distribution_failure = static_cast<u8>(80 + (result.code & 63)); return false; }
    return true;
}

bool distribution_snapshot(daemon& server, provisioning_reply& reply) {
    provisioning_request request{}; request.operation = provisioning_operation::checkpoint;
    if (!provisioning_expect(server.control, request, reply, status::ok)) { distribution_failure = 60; return false; }
    return true;
}
bool distribution_selected(daemon& server, u64 sequence, u64 generation, u32 count) {
    provisioning_reply reply{};
    if (!distribution_snapshot(server, reply)) return false;
    const auto& catalog = reply.candidate.catalog;
    if (reply.candidate.checkpoint.sequence != sequence || catalog.count != count ||
        catalog.active >= count || catalog.roots[catalog.active].generation != generation) {
        distribution_failure = 61; return false;
    }
    return true;
}

u32 distribution_visible_owned_channels() {
    u32 owned = 0;
    for (u32 i = 0; i < 32; ++i) {
        channel_info info{};
        const auto result = sdk::channel_get(i, info);
        if (result == thread_error_not_found) return owned;
        if (result || info.version != channel_version || info.size != sizeof(info)) return ~u32{0};
        if (info.controller_pid == sdk::pid()) ++owned;
    }
    return ~u32{0};
}
void distribution_diagnostic(distribution_logs& logs, const execution::launch_diagnostic& diagnostic,
                             i64 result, const process_stats& statistics, u32 channels,
                             const anchor_guest::pair& backing) {
    char text[256]{}; u32 length = 0;
    const auto append = [&](const char* value) { while (*value && length + 1 < sizeof(text)) text[length++] = *value++; };
    const auto number = [&](i64 value) {
        if (value < 0) { if (length + 1 < sizeof(text)) text[length++] = '-'; value = -value; }
        char digits[24]; u32 count = 0;
        do { digits[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value && count < sizeof(digits));
        while (count && length + 1 < sizeof(text)) text[length++] = digits[--count];
    };
    append("P1D_LAUNCH stage="); number(static_cast<i64>(diagnostic.stage));
    append(" code="); number(diagnostic.code); append(" result="); number(result);
    append(" elf="); number(static_cast<i64>(diagnostic.format_error));
    append(" tasks="); number(statistics.tasks); append(" completions="); number(statistics.completions);
    append(" free_pages="); number(statistics.free_pages); append(" legacy_visible_owned="); number(channels);
    append(" created_backing_send="); number(backing.transmit);
    append(" created_backing_receive="); number(backing.receive); append("\n");
    if (logs.files.set_deadline(storage::exchange_deadline()))
        (void)logs.files.write(logs.handles[1], text, length);
}

bool distribution_launch(daemon& server) {
    catalog::authority binding{catalog::authority_version, sizeof(catalog::authority), server.pid, {}, {}};
    __builtin_memcpy(binding.realm, anchored_installation_realm.bytes, sizeof(binding.realm));
    __builtin_memcpy(binding.service, disk_test_service, sizeof(disk_test_service));
    const auto installed = dynamic::install_anchored(binding, storage::exchange_deadline());
    if (installed != dynamic::error::none) { distribution_failure = static_cast<u8>(160 + static_cast<u32>(installed)); return false; }
    dynamic::launch_policy policy{};
    if (dynamic::export_policy(policy) != dynamic::error::none) { distribution_failure = 62; return false; }
    static dynamic::closure closure{};
    if (dynamic::acquire_index(policy.active, storage::exchange_deadline(), closure) != dynamic::error::none) {
        distribution_failure = 63; return false;
    }
    char executable[128]; __builtin_memcpy(executable, closure.value.objects[2].path, sizeof(executable));
    if (dynamic::release(closure) != 0) { distribution_failure = 64; return false; }
    static distribution_logs logs;
    sdk::spawn_options options{};
    options.prepare_child = [](u64 child, void*) {
        return sdk::syscall(sys_process_authority, child, static_cast<u64>(process_authority_mode::copy_from_caller));
    };
    if (!logs.open("/dist/application.out", "/dist/application.err", options)) { distribution_failure = 65; return false; }
    const auto channels = distribution_visible_owned_channels();
    const bool backing_created = server.backing_channels.transmit && server.backing_channels.receive &&
        server.backing_channels.transmit != server.backing_channels.receive;
    const auto statistics = sdk::stats();
    execution::launch_diagnostic diagnostic{}; execution::image_receipt receipt{};
    const char* arguments[]{executable};
    i64 child = process_error_resources;
    // Enumeration shows participants, not owner-only channels. The actual
    // daemon->proxy create_pair results are retained and each peer validates
    // its owner/opposite peer. No legacy control pair is additionally visible;
    // the real loader still must complete its own READY/ACK exchange.
    if (channels == 0 && backing_created)
        child = execution::spawn_file_diagnosed_receipt(executable, 1, arguments, options, diagnostic, receipt);
    distribution_diagnostic(logs, diagnostic, child, statistics, channels, server.backing_channels);
    const bool closed = logs.close();
    if (child <= 0 || !closed) {
        if (child > 0) { (void)sdk::syscall(10, static_cast<u64>(child)); process_status ignored{}; (void)sdk::wait(child, ignored); }
        distribution_failure = channels != 0 || !backing_created ? 69 : static_cast<u8>(210 + (-child & 31)); return false;
    }
    process_status result{};
    if (sdk::wait(static_cast<u64>(child), result) || result.outcome != process_outcome::exited || result.code) {
        distribution_failure = 66; return false;
    }
    return true;
}

bool distribution_probe(daemon& server, u8 scenario) {
    provisioning_reply before{}, after{};
    if (!distribution_snapshot(server, before)) return false;
    if (scenario == 32) {
        if (before.candidate.checkpoint.sequence || before.candidate.catalog.count ||
            !distribution_run(server, "/dist/v1", "/dist/v1/lock.json", 0)) return false;
        return distribution_selected(server, 1, 1101, 1) && distribution_launch(server);
    }
    if (scenario == 35) {
        return distribution_run(server, "/dist/v2", "/dist/v2/lock.json", 0) &&
            distribution_selected(server, 2, 1102, 2) && distribution_launch(server);
    }
    if (scenario == 33) {
        if (!distribution_run(server, "/dist/v1", "/dist/v1/lock.json", 3, false, false)) return false;
        constexpr const char* cases[]{"altered", "expired", "untrusted", "cycle", "conflict", "missing", "changedobject"};
        for (const auto* selected : cases) {
            char repository[64] = "/dist/", lock[80] = "/dist/";
            u32 length = 6;
            for (u32 i = 0; selected[i]; ++i) repository[length++] = selected[i];
            repository[length] = 0; __builtin_memcpy(lock, repository, length);
            __builtin_memcpy(lock + length, "/lock.json", 11);
            if (!distribution_run(server, repository, lock, 3)) return false;
        }
    } else if (scenario == 34) {
        if (!distribution_run(server, "/dist/v2", "/dist/v2/lock.json", 70, true)) return false;
    } else if (scenario == 36) {
        if (!distribution_run(server, "/dist/v1", "/dist/v1/lock.json", 3)) return false;
    } else return false;
    if (!distribution_snapshot(server, after) || __builtin_memcmp(&before.current, &after.current, sizeof(before.current)) ||
        __builtin_memcmp(&before.candidate, &after.candidate, sizeof(before.candidate))) {
        distribution_failure = 67; return false;
    }
    return distribution_selected(server, scenario == 36 ? 2 : 1, scenario == 36 ? 1102 : 1101,
                                 scenario == 36 ? 2 : 1) && distribution_launch(server);
}
