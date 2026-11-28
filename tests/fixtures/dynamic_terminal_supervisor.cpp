// SPDX-License-Identifier: Apache-2.0
// Explicit test supervisor with compile-time approved roots and a real COM1 actor.
#include <xos/dynamic_launch.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <xos/terminal_control.hpp>
#include <xos/thread_abi.hpp>
#include "dynamic_roots.hpp"
#include "public_runtime/terminal_owner_evidence.h"

namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker descriptor_receiver{
    exec_image_abi_magic, 3, sizeof(exec_marker)};
terminal::control terminal_session;
terminal::application application;
bool observe_registration_budget;
u64 attached_ipc_objects;
struct packet { u64 kind, value; };
u64 now() { const i64 value = sdk::syscall(sys_clock_monotonic); return value > 0 ? static_cast<u64>(value) : 0; }
bool transmit(const char* text) {
    const auto size = static_cast<u32>(sdk::length(text));
    return size <= terminal::data_bytes &&
        terminal::write_until(terminal_session, text, size, now() + 2'000'000'000) == size;
}
bool transmit_number(u64 value) {
    char text[24]{}; u32 end = sizeof(text) - 1;
    do { text[--end] = static_cast<char>('0' + value % 10); value /= 10; } while (value);
    return transmit(text + end);
}
[[noreturn]] void fail(const char* label, i64 code = 0) {
    if (terminal_session.child) {
        (void)transmit("DYNAMIC_TERMINAL_SUPERVISOR_FAIL "); (void)transmit(label);
        (void)transmit(" code=");
        if (code < 0) (void)transmit("-");
        (void)transmit_number(code < 0 ? u64{0} - static_cast<u64>(code) : static_cast<u64>(code));
        (void)transmit("\n");
    }
    sdk::print("DYNAMIC_TERMINAL_SUPERVISOR_FAIL "); sdk::print(label);
    sdk::print(" code="); sdk::signed_decimal(code); sdk::print("\n"); sdk::exit(91);
}
void need(bool good, const char* label, i64 code = 0) { if (!good) fail(label, code); }
bool same(const process_stats& a, const process_stats& b) {
    return a.free_pages == b.free_pages && a.tasks == b.tasks && a.completions == b.completions &&
        a.reserved == b.reserved;
}
void diagnostic_text(const char* value) {
    if (terminal_session.child) (void)transmit(value);
    sdk::print(value);
}
void diagnostic_number(u64 value) {
    if (terminal_session.child) (void)transmit_number(value);
    sdk::signed_decimal(static_cast<i64>(value));
}
void diagnostic_stats(const process_stats& value) {
    diagnostic_number(value.free_pages); diagnostic_text(",");
    diagnostic_number(value.tasks); diagnostic_text(",");
    diagnostic_number(value.completions); diagnostic_text(",");
    diagnostic_number(value.reserved);
}
void settled(const process_stats& expected, const char* phase) {
    const u64 deadline = now() + 5'000'000'000;
    for (;;) {
        const auto observed = sdk::stats();
        if (same(expected, observed)) return;
        if (now() >= deadline) {
            diagnostic_text("DYNAMIC_TERMINAL_RESOURCE_MISMATCH phase="); diagnostic_text(phase);
            diagnostic_text(" expected="); diagnostic_stats(expected);
            diagnostic_text(" actual="); diagnostic_stats(observed); diagnostic_text("\n");
            fail(phase);
        }
        sdk::yield();
    }
}
void close_pipe(u32 handle) { need(sdk::syscall(sys_pipe_close, handle) == 0, "pipe-close"); }
i64 prepared() {
    static constexpr char name[] = "ttyquota";
    return sdk::syscall(sys_process_create, 0, reinterpret_cast<u64>(name), sizeof(name) - 1);
}
void channel_quota() {
    const auto baseline = sdk::stats();
    const i64 child = prepared(); need(child > 0, "quota-child", child);
    channel_create request{1, sizeof(request), sdk::pid(), static_cast<u64>(child), 1, 0};
    u32 handles[6]{};
    for (u32 i = 0; i < 4; ++i) {
        const i64 result = sdk::channel_open(request); need(result > 0, "legacy-four", result);
        handles[i] = static_cast<u32>(result);
    }
    need(sdk::channel_open(request) == process_error_resources, "legacy-fifth-denied");
    for (u32 i = 4; i < 6; ++i) {
        const i64 result = sdk::channel_open_extended(request); need(result > 0, "explicit-six", result);
        handles[i] = static_cast<u32>(result);
    }
    need(sdk::channel_open_extended(request) == process_error_resources, "extended-seventh-denied");
    need(sdk::channel_open(request) == process_error_resources, "no-implicit-legacy-upgrade");
    need(sdk::syscall(sys_channel, 7, reinterpret_cast<u64>(&request), 1) == process_error_invalid,
         "extended-third-zero");
    request.reserved = 1; need(sdk::channel_open_extended(request) == process_error_invalid, "extended-reserved-zero");
    request.reserved = 0; request.version = 2;
    need(sdk::channel_open_extended(request) == process_error_invalid, "extended-version");
    request.version = 1; request.capacity = 0;
    need(sdk::channel_open_extended(request) == process_error_invalid, "extended-capacity");
    request.capacity = 1; request.receiver_pid = ~u64{0};
    need(sdk::channel_open_extended(request) == process_error_denied, "extended-foreign-pid");
    for (u32 handle : handles) need(sdk::channel_close(handle) == 0, "quota-close");
    need(sdk::syscall(sys_process_abort, static_cast<u64>(child)) == 0, "quota-abort");
    settled(baseline, "native-channel-quota-cleanup");
}
void budget_quota() {
    const process_budget_vector limits{4, 65536, 16, 5, 2, 8};
    need(sdk::set_process_budget(sdk::pid(), limits) == 0, "budget-self-restrict");
    process_budget_snapshot before{}, after{};
    need(sdk::query_process_budget(sdk::pid(), before) == 0 && before.domain_id &&
         before.usage.ipc_objects == 0, "budget-before");
    const auto baseline = sdk::stats();
    const i64 child = prepared(); need(child > 0, "budget-child", child);
    channel_create request{1, sizeof(request), sdk::pid(), static_cast<u64>(child), 1, 0};
    u32 handles[5]{};
    for (u32& handle : handles) {
        const i64 result = sdk::channel_open_extended(request); need(result > 0, "budget-five", result);
        handle = static_cast<u32>(result);
    }
    need(sdk::query_process_budget(sdk::pid(), after) == 0 && after.usage.ipc_objects == 5, "budget-count-five");
    need(sdk::channel_open_extended(request) == process_error_resources, "budget-denies-sixth");
    for (u32 handle : handles) need(sdk::channel_close(handle) == 0, "budget-close");
    need(sdk::syscall(sys_process_abort, static_cast<u64>(child)) == 0, "budget-abort");
    settled(baseline, "native-budget-quota-cleanup");
    need(sdk::query_process_budget(sdk::pid(), after) == 0 && after.domain_id == before.domain_id &&
         after.usage.processes == before.usage.processes && after.usage.pages == before.usage.pages &&
         after.usage.threads == before.usage.threads && after.usage.ipc_objects == 0 &&
         after.usage.names == before.usage.names && after.usage.pipes == before.usage.pipes, "budget-all-credits-returned");
}
void start_actor() {
    need(terminal::start(terminal_session, "/bin/terminal.elf") > 0, "actor-start");
}
void stop_actor() {
    terminal::request request{}; terminal::response response{};
    request.operation = static_cast<u32>(terminal::operation::stop);
    need(terminal::exchange(terminal_session, request, response) == 0 && response.result == 0, "actor-stop");
    process_status status{};
    need(sdk::wait(terminal_session.child, status) == 0 && status.outcome == process_outcome::exited &&
         status.code == 0, "actor-stop-wait");
    terminal::close(terminal_session);
    need(sdk::pio_grant(pio_grant_action::query, 0, pio_resource_com1) == 2 &&
         sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) == 0, "actor-stop-recover");
}
i64 attach(u64 child, void* context) {
    const bool authority = *static_cast<const bool*>(context);
    const i64 permission = sdk::syscall(sys_process_authority, child,
        static_cast<u64>(authority ? process_authority_mode::copy_from_caller : process_authority_mode::clear));
    if (permission != 0) return permission;
    const i64 result = terminal::attach(terminal_session, application, child);
    if (result == 0 && observe_registration_budget) {
        process_budget_snapshot state{};
        const i64 queried = sdk::query_process_budget(sdk::pid(), state);
        if (queried != 0) return queried;
        attached_ipc_objects = state.usage.ipc_objects;
    }
    return result;
}
packet receive(u32 handle, u64 expected, u64 budget = 10'000'000'000,
               u64* elapsed = nullptr) {
    packet result{}; u32 offset = 0;
    const u64 began = now();
    const u64 deadline = began + budget;
    while (offset < sizeof(result)) {
        need(launch::poll() == 0, "control-pump");
        const i64 count = sdk::syscall(sys_pipe_read, handle,
            reinterpret_cast<u64>(reinterpret_cast<u8*>(&result) + offset), sizeof(result) - offset);
        if (count == process_error_would_block) { need(now() < deadline, "packet-deadline"); sdk::yield(); continue; }
        need(count > 0 && static_cast<u64>(count) <= sizeof(result) - offset, "packet-read", count);
        offset += static_cast<u32>(count);
    }
    if (result.kind != expected) {
        (void)transmit("DYNAMIC_TERMINAL_PACKET_FAILURE expected="); (void)transmit_number(expected);
        (void)transmit(" actual="); (void)transmit_number(result.kind); (void)transmit("\n");
        fail("packet-kind", static_cast<i64>(result.value));
    }
    if (elapsed) *elapsed = now() - began;
    return result;
}
void release(u32 handle) {
    static constexpr char value = 'G';
    need(sdk::syscall(sys_pipe_write, handle, reinterpret_cast<u64>(&value), 1) == 1, "release-child");
}
void run_case(const char* name, bool expect_start_failure = false) {
    const auto baseline = sdk::stats();
    pipe_handles ready{}, go{};
    need(sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&ready)) == 0 &&
         sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&go)) == 0, "control-pipes");
    const startup_descriptor descriptors[]{
        {0, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
        {1, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
        {2, 0, static_cast<u32>(startup_fd_kind::terminal), 0, 2, 0},
        {3, 1, static_cast<u32>(startup_fd_kind::pipe_write), ready.write_token, 1, 0},
        {4, 2, static_cast<u32>(startup_fd_kind::pipe_read), go.read_token, 0, 0},
    };
    bool authority = !sdk::equal(name, "authority");
    observe_registration_budget = expect_start_failure; attached_ipc_objects = 0;
    sdk::spawn_options options{};
    for (u32 i = 0; i < 3; ++i) options.stdio[i] = -2;
    options.prepare_child = attach; options.prepare_context = &authority;
    options.terminal_send_handle = &application.incoming;
    options.descriptors = descriptors; options.descriptor_count = 5;
    options.transfer_independent_pipes = true;
    const char* argv[]{dynamic_run_main_paths[0], name};
    const i64 child = sdk::spawn_file_options(argv[0], 2, argv, options);
    if (expect_start_failure) {
        need(child == process_error_resources && application.peer && attached_ipc_objects == 4,
             "partial-launch-pair-denial-after-actor-attach", child);
        close_pipe(ready.read_token); close_pipe(ready.write_token);
        close_pipe(go.read_token); close_pipe(go.write_token);
        need(terminal::detach(terminal_session, application) == 0, "failed-start-detach");
        settled(baseline, "partial-launch-pair-cleanup");
        process_budget_snapshot state{};
        need(sdk::query_process_budget(sdk::pid(), state) == 0 && state.usage.ipc_objects == 2,
             "partial-registration-all-references-returned");
        need(transmit("DYNAMIC_TERMINAL_START_ROLLBACK_PASS actor_channels=2\n"), "rollback-marker");
        return;
    }
    need(child > 0, "dynamic-terminal-start", child);
    close_pipe(ready.write_token); close_pipe(go.read_token);
    process_status status{};
    u64 positive_elapsed = 0;
    bool positive_completed = false;
    if (sdk::equal(name, "owner-exit")) {
        const packet descendant = receive(ready.read_token, 2);
        need(sdk::wait(static_cast<u64>(child), status) == 0 && status.outcome == process_outcome::exited &&
             status.code == 0, "controller-normal-exit");
        release(go.write_token);
        const packet completed = receive(ready.read_token, 3);
        need(completed.value == descendant.value && completed.value != static_cast<u64>(child), "orphan-identity");
    } else if (sdk::equal(name, "owner-kill")) {
        const packet descendant = receive(ready.read_token, 2);
        need(descendant.value != static_cast<u64>(child), "cancel-descendant");
        need(sdk::syscall(sys_process_cancel, static_cast<u64>(child)) == 0, "controller-cancel");
        need(sdk::wait(static_cast<u64>(child), status) == 0 && status.outcome == process_outcome::killed,
             "controller-cancel-wait");
    } else if (sdk::equal(name, "actor-death")) {
        need(receive(ready.read_token, 1).value == static_cast<u64>(child), "actor-death-child-ready");
        need(sdk::syscall(sys_process_cancel, terminal_session.child) == 0, "actor-cancel");
        need(sdk::wait(terminal_session.child, status) == 0 && status.outcome == process_outcome::killed,
             "actor-cancel-wait");
        terminal::close(terminal_session); terminal::close(application);
        release(go.write_token);
        need(receive(ready.read_token, 3).value == static_cast<u64>(child), "actor-death-survivor-pid-fds");
        need(sdk::wait(static_cast<u64>(child), status) == 0 && status.outcome == process_outcome::exited &&
             status.code == 0, "actor-death-survivor-exit");
        need(sdk::pio_grant(pio_grant_action::recover, 0, pio_resource_com1) == 0, "actor-explicit-recovery");
        start_actor();
    } else {
        // This completion spans fork admission, failed and successful exec,
        // and post-exec I/O. Each generation retains its 30-second startup
        // budget; this aggregate is not the individual fork/exec deadline.
        (void)receive(ready.read_token, 3, 65'000'000'000, &positive_elapsed);
        need(sdk::wait(static_cast<u64>(child), status) == 0 && status.outcome == process_outcome::exited &&
             status.code == 0, "positive-child-wait");
        positive_completed = true;
    }
    close_pipe(ready.read_token); close_pipe(go.write_token);
    // The completion packet follows the orphan's last terminal operation.
    // Detach joins the actor's application worker; the final baseline then
    // also waits for ordinary orphans to finish in the kernel reaper.
    if (application.peer) need(terminal::detach(terminal_session, application) == 0, "application-detach");
    settled(baseline, "normal-case-cleanup");
    if (positive_completed)
        need(transmit("DYNAMIC_TERMINAL_COMPLETION_TIMING ") && transmit(name) &&
             transmit(" packet_wait_ns=") && transmit_number(positive_elapsed) && transmit("\n"),
             "positive-completion-timing");
    if (sdk::equal(name, "owner-exit"))
        need(transmit("DYNAMIC_TERMINAL_CONTROLLER_EXIT_CLOSED_FOREGROUND_PASS\n"), "controller-exit-marker");
    need(transmit("DYNAMIC_TERMINAL_CASE_PASS ") && transmit(name) && transmit(" resources=") &&
         transmit_number(baseline.free_pages) && transmit(",") && transmit_number(baseline.tasks) &&
         transmit(",") && transmit_number(baseline.completions) && transmit("\n"), "case-marker");
}
}

// Native owner-death observer and driver are separate test roles in this
// identical ELF; their declarations are implemented below.
namespace {
[[noreturn]] void observe_owner_death(const xos::startup_info*, const char*, const char*);
[[noreturn]] void terminal_owner_death(bool);
}

extern "C" int xos_user_main(const xos::startup_info* startup) {
    using namespace xos;
    if (startup != nullptr && startup->argc == 4) {
        const auto* argv = reinterpret_cast<const char* const*>(startup->argv);
        if (sdk::equal(argv[1], "owner-observer")) observe_owner_death(startup, argv[2], argv[3]);
    }
    for (u64 demo = 1; demo <= 4; ++demo) (void)sdk::syscall(10, demo);
    sdk::print("DYNAMIC_TERMINAL_BOOT_READY\n");
    char trigger = 0;
    while (sdk::read(0, &trigger, 1) != 1) sdk::yield();
    need(trigger == '!' || trigger == 'C' || trigger == 'D', "explicit-probe-trigger");
    need(dynamic_run_approved.count == 1 && dynamic::install(dynamic_run_approved, now() + 5'000'000'000)
         == dynamic::error::none, "approved-terminal-policy");
    if (trigger != '!') terminal_owner_death(trigger == 'C');
    channel_quota();
    start_actor(); need(transmit("DYNAMIC_TERMINAL_CHANNEL_LIMITS_PASS\n"), "limits-marker");
    const char* cases[]{"direct", "fork", "authority", "owner-exit", "owner-kill", "actor-death"};
    for (u32 round = 0; round < 2; ++round)
        for (const char* name : cases) run_case(name);
    stop_actor();
    budget_quota();
    start_actor();
    // The completed actor roundtrip precedes run_case's resource snapshot:
    // its permanent receive/control workers must already exist in that baseline.
    need(transmit("DYNAMIC_TERMINAL_BUDGET_QUOTA_PASS\n"), "budget-quota-marker");
    run_case("direct", true);
    need(transmit("DYNAMIC_TERMINAL_BUDGET_PASS\n") &&
         transmit("DYNAMIC_TERMINAL_ALL_PASS cases=13 native_groups=2\n"), "complete-marker");
    stop_actor(); return 0;
}

#include "dynamic_terminal_owner_probe.hpp"
