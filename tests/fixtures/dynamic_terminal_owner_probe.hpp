// SPDX-License-Identifier: Apache-2.0
// Test-only roles included into the explicit terminal supervisor.
namespace {
void decimal_text(u64 value, char* output) {
    char reverse[24]{}; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
    for (u32 i = 0; i < count; ++i) output[i] = reverse[count - i - 1];
    output[count] = 0;
}
bool parse_token(const char* text, u32& output) {
    if (text == nullptr || *text == 0) return false;
    u64 value = 0;
    for (u32 i = 0; text[i]; ++i) {
        if (i >= 10 || text[i] < '0' || text[i] > '9') return false;
        value = value * 10 + static_cast<u32>(text[i] - '0');
        if (value > 0xffffffffu) return false;
    }
    output = static_cast<u32>(value); return output != 0;
}
i64 pipe_record(u32 handle, void* raw, u32 size, u64 deadline) {
    auto* bytes = static_cast<u8*>(raw); u32 offset = 0;
    while (offset < size) {
        const i64 count = sdk::syscall(sys_pipe_read, handle, reinterpret_cast<u64>(bytes + offset), size - offset);
        if (count == process_error_would_block) {
            if (now() >= deadline) return thread_error_timeout;
            sdk::yield(); continue;
        }
        if (count <= 0 || static_cast<u64>(count) > size - offset) return count == 0 ? process_error_state : count;
        offset += static_cast<u32>(count);
    }
    return 0;
}
i64 pipe_eof(u32 handle, u64 deadline) {
    u8 byte = 0;
    for (;;) {
        const i64 count = sdk::syscall(sys_pipe_read, handle, reinterpret_cast<u64>(&byte), 1);
        if (count == 0) return 0;
        if (count != process_error_would_block) return count < 0 ? count : process_error_state;
        if (now() >= deadline) return thread_error_timeout;
        sdk::yield();
    }
}
observe_native::snapshot observe_self() {
    const observe_native::request request{1, sizeof(request), observe_native::query::resources, 0,
        0, sdk::pid(), 1, now() + 2'000'000'000};
    observe_native::snapshot result{};
    need(sdk::observe(request, result) == observe_native::result::ok, "owner-self-observation");
    return result;
}
[[noreturn]] void observe_owner_death(const startup_info* startup, const char* owner_token, const char* events_token) {
    static_assert(sizeof(owner_event) == 256 && sizeof(owner_setup) == 256 && sizeof(owner_report) == 1224);
    owner_report report{};
    report.magic = OWNER_REPORT_MAGIC; report.version = OWNER_REPORT_VERSION; report.size = sizeof(report);
    report.observer_pid = sdk::pid();
    file::client files; const bool files_ready = files.init();
    const u64 deadline = now() + 30'000'000'000;
    const auto capture = [&]() -> bool {
#define OWNER_NEED(value, code) do { if (!(value)) { report.failure_line = __LINE__; \
    report.failure_code = static_cast<owner_u64>(code); return false; } } while (0)
        OWNER_NEED(files_ready && files.set_deadline(deadline), process_error_state);
        u32 length = 0;
        OWNER_NEED(files.read_all("/tests/terminal_nonce", report.nonce, sizeof(report.nonce), length) == 0 &&
            length == sizeof(report.nonce), process_error_invalid);
        u32 owner = 0, events = 0;
        OWNER_NEED(parse_token(owner_token, owner) && parse_token(events_token, events) && owner != events,
            process_error_invalid);
        OWNER_NEED(startup != nullptr && startup->magic == startup_magic && startup->version == 3 &&
            startup->size == sizeof(startup_info), process_error_invalid);
        const auto* extension = reinterpret_cast<const startup_exec_extension*>(
            reinterpret_cast<const u8*>(startup) + startup_exec_offset);
        OWNER_NEED(extension->magic == startup_exec_magic && extension->count == 2 && !extension->reserved &&
            extension->descriptors >= process_startup_begin &&
            extension->descriptors <= process_stack_top - 2 * sizeof(startup_descriptor), process_error_invalid);
        const auto* descriptors = reinterpret_cast<const startup_descriptor*>(extension->descriptors);
        for (u32 i = 0; i < 2; ++i) {
            const auto& item = descriptors[i];
            OWNER_NEED(item.fd == i + 3 && item.object == i && item.kind == 3 && !item.flags && !item.reserved &&
                item.handle == (i == 0 ? owner : events), process_error_invalid);
        }
        // A spawned observer has no bootstrap-supervisor privilege. Record the
        // real denial and unchanged output instead of treating an ignored error
        // as a zero-valued global resource observation.
        const process_stats sentinel{0x4f574e52u, 0x4f574e52u, 0x4f574e52u, 0x4f574e52u};
        process_stats inaccessible = sentinel;
        const i64 denied = sdk::syscall(sys_process_stats, reinterpret_cast<u64>(&inaccessible));
        report.process_stats_query_result = static_cast<owner_u64>(denied);
        OWNER_NEED(denied == process_error_denied && same(inaccessible, sentinel), denied);
        i64 result = pipe_record(owner, &report.setup, sizeof(report.setup), deadline);
        OWNER_NEED(result == 0, result);
        OWNER_NEED(report.setup.value[os_owner] != report.observer_pid && report.setup.value[os_control] <= 1,
            process_error_state);
        // The owner retains this writer until actual process exit. Native
        // parent=0 below independently confirms reparenting after that death.
        result = pipe_eof(owner, deadline); OWNER_NEED(result == 0, result);
        if (!report.setup.value[os_control]) {
            for (u32 i = 0; i < 3; ++i) {
                result = pipe_record(events, &report.events[i], sizeof(owner_event), deadline);
                OWNER_NEED(result == 0 && report.events[i].value[oe_kind] == i + 1, result);
            }
        }
        result = pipe_eof(events, deadline); OWNER_NEED(result == 0, result);
        OWNER_NEED(sdk::syscall(sys_pipe_close, owner) == 0 && sdk::syscall(sys_pipe_close, events) == 0,
            process_error_state);
        thread_stats previous{}; u64 unchanged = now();
        for (;;) {
            thread_stats current{};
            const i64 queried = sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&current));
            report.thread_stats_query_result = static_cast<owner_u64>(queried);
            OWNER_NEED(queried == 0, queried);
            OWNER_NEED(current.header.version == thread_abi_version &&
                current.header.size == sizeof(current) && !current.header.reserved, process_error_state);
            if (current.processes != previous.processes || current.free_pages != previous.free_pages ||
                current.threads != previous.threads || current.reserved != previous.reserved ||
                current.waiting != previous.waiting || current.results != previous.results ||
                current.process_user_pages != previous.process_user_pages ||
                current.process_kernel_stack_pages != previous.process_kernel_stack_pages) unchanged = now();
            previous = current;
            report.free_pages = current.free_pages; report.tasks = current.processes;
            report.observer_thread_results = current.results;
            report.observer_user_pages = current.process_user_pages;
            report.observer_kernel_stack_pages = current.process_kernel_stack_pages;
            report.observer_threads = current.threads;
            report.observer_reserved_threads = current.reserved;
            report.observer_waiting_threads = current.waiting;
            report.stable_ns = now() - unchanged;
            if (current.processes == 2 && current.threads == 1 && current.reserved == 0 &&
                current.waiting == 0 && current.results == 0 && report.stable_ns >= 250'000'000) break;
            OWNER_NEED(now() < deadline, thread_error_timeout); sdk::yield();
        }
        const observe_native::request request{1, sizeof(request), observe_native::query::resources, 0,
            0, sdk::pid(), 1, now() + 2'000'000'000};
        observe_native::snapshot snapshot{};
        OWNER_NEED(sdk::observe(request, snapshot) == observe_native::result::ok &&
            snapshot.parent_pid == 0 && snapshot.pipe_references == 0 && snapshot.owned_channels == 0 &&
            snapshot.pages == previous.process_user_pages, process_error_state);
        report.observer_parent = snapshot.parent_pid;
        report.observer_channels = snapshot.owned_channels; report.observer_pipe_references = snapshot.pipe_references;
        return true;
#undef OWNER_NEED
    };
    report.status = capture() ? 1 : 0;
    if (files_ready && files.set_deadline(now() + 5'000'000'000)) {
        const i64 written = files.replace("/tests/terminal_owner_report", &report, sizeof(report));
        // A separate nonce witness is created only after the report's real
        // sync succeeds. A stale witness cannot authorize this run's nonce.
        if (written == 0 && files.sync() == 0 && report.status == 1 &&
            files.replace("/tests/terminal_owner_synced", report.nonce, sizeof(report.nonce)) == 0)
            (void)files.sync();
    }
    // Keep the measured observer+Files state alive. The host only accepts the
    // nonce-bound durable file after it stops QEMU and cold-reads the disk.
    for (;;) (void)sdk::syscall(sys_sleep_until, now() + 1'000'000'000);
}
[[noreturn]] void terminal_owner_death(bool control) {
    pipe_handles ready{}, go{}, owner{}, events{};
    pipe_handles* all_pipes[]{&ready, &go, &owner, &events};
    for (auto* pipe : all_pipes)
        need(sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(pipe)) == 0, "owner-evidence-pipe");
    char owner_token[24]{}, events_token[24]{};
    decimal_text(owner.read_token, owner_token); decimal_text(events.read_token, events_token);
    const startup_descriptor observer_descriptors[]{
        {3, 0, static_cast<u32>(startup_fd_kind::pipe_read), owner.read_token, 0, 0},
        {4, 1, static_cast<u32>(startup_fd_kind::pipe_read), events.read_token, 0, 0},
    };
    sdk::spawn_options observer_options{};
    for (u32 i = 0; i < 3; ++i) observer_options.stdio[i] = -2;
    observer_options.descriptors = observer_descriptors; observer_options.descriptor_count = 2;
    observer_options.transfer_independent_pipes = true;
    const char* observer_argv[]{"/usr/bin/terminal-supervisor", "owner-observer", owner_token, events_token};
    const i64 observer = sdk::spawn_file_options(observer_argv[0], 4, observer_argv, observer_options);
    need(observer > 0, "owner-independent-observer", observer);
    close_pipe(owner.read_token); close_pipe(events.read_token);
    owner_setup setup{}; setup.value[os_control] = control; setup.value[os_owner] = sdk::pid();
    const auto baseline = sdk::stats();
    setup.value[os_baseline_pages] = baseline.free_pages; setup.value[os_baseline_tasks] = baseline.tasks;
    setup.value[os_baseline_completions] = baseline.completions;
    if (!control) {
        start_actor(); setup.value[os_actor] = terminal_session.child;
        const startup_descriptor descriptors[]{
            {0, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
            {1, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
            {2, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
            {3, 1, static_cast<u32>(startup_fd_kind::pipe_write), ready.write_token, 1, 0},
            {4, 2, static_cast<u32>(startup_fd_kind::pipe_read), go.read_token, 0, 0},
            {5, 3, static_cast<u32>(startup_fd_kind::pipe_write), events.write_token, 1, 0},
        };
        bool authority = true;
        sdk::spawn_options options{};
        for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
        options.prepare_child = attach; options.prepare_context = &authority;
        options.terminal_send_handle = &application.incoming;
        options.descriptors = descriptors; options.descriptor_count = 6;
        options.transfer_independent_pipes = true;
        const char* argv[]{dynamic_run_main_paths[0], "terminal-owner-death"};
        const i64 child = sdk::spawn_file_options(argv[0], 2, argv, options);
        need(child > 0, "owner-death-controller-start", child);
        setup.value[os_controller] = static_cast<u64>(child);
        close_pipe(ready.write_token); close_pipe(go.read_token); close_pipe(events.write_token);
        setup.value[os_child] = receive(ready.read_token, 5).value;
        setup.value[os_pending_seen_ns] = now();
    } else {
        close_pipe(ready.write_token); close_pipe(go.read_token); close_pipe(events.write_token);
    }
    close_pipe(ready.read_token); close_pipe(go.write_token);
    thread_stats threads{};
    need(sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&threads)) == 0, "owner-thread-account");
    const auto own = observe_self(); const auto before = sdk::stats();
    setup.value[os_before_pages] = before.free_pages; setup.value[os_before_tasks] = before.tasks;
    setup.value[os_before_completions] = before.completions;
    setup.value[os_owner_user_pages] = threads.process_user_pages;
    setup.value[os_owner_kernel_stack_pages] = threads.process_kernel_stack_pages;
    setup.value[os_owner_channels] = own.owned_channels;
    setup.value[os_owner_pipe_references] = own.pipe_references;
    setup.value[os_exit_started_ns] = now();
    need(sdk::syscall(sys_pipe_write, owner.write_token, reinterpret_cast<u64>(&setup), sizeof(setup))
        == sizeof(setup), "owner-final-record");
    // Do not close the owner writer or any terminal channels manually: exit
    // must be the event which invalidates them and wakes the pending read.
    sdk::exit(0);
}
}
