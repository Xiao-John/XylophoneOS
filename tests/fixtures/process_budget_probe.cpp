// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include <xos/dynamic_launch.hpp>
#include <xos/ipc_v1.hpp>
#include <xos/thread_abi.hpp>
#include <xos/vm_abi.hpp>
namespace {
using namespace xos;
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker exec_metadata{exec_image_abi_magic, 3, sizeof(exec_marker)};
[[noreturn]] void fail(const char* name, i64 result = 0) {
    sdk::print("P1B_FAIL "); sdk::print(name); sdk::print(" result=");
    sdk::signed_decimal(result); sdk::print("\n"); sdk::exit(91);
}
void need(bool good, const char* name, i64 result = 0) { if (!good) fail(name, result); }
u64 now() { const auto value = sdk::syscall(sys_clock_monotonic); need(value > 0, "clock"); return static_cast<u64>(value); }
void pause(u64 ns) { need(!sdk::syscall(sys_sleep_until, now() + ns), "sleep"); }
process_budget_snapshot snapshot(u64 domain = 0) {
    process_budget_snapshot result{};
    const auto status = sdk::query_process_budget(sdk::pid(), result, domain);
    need(!status && result.version == 1 && result.size == sizeof(result) && result.pid == sdk::pid(), "query", status);
    return result;
}
process_budget_vector limits(u64 processes = 3) {
    const auto own = snapshot();
    return {processes, own.attributed.pages * processes + 512, processes, 4, 2, 2};
}
i64 fork_child() {
    const i64 child = sdk::syscall(sys_process_fork_prepare);
    if (child <= 0) return child;
    file::client files; need(files.init(), "fork-files-init");
    i64 cloned = static_cast<i64>(file::status::would_block);
    const u64 end = now() + 2'000'000'000;
    while (cloned == static_cast<i64>(file::status::would_block) && now() < end) {
        cloned = files.clone_session(static_cast<u64>(child));
        if (cloned == static_cast<i64>(file::status::would_block)) sdk::yield();
    }
    need(!cloned, "fork-files-clone", cloned);
    need(!sdk::syscall(sys_process_fork_commit, static_cast<u64>(child)), "fork-commit");
    return child;
}
void wait_child(i64 child) {
    need(child > 0, "positive-child", child);
    process_status status{};
    need(!sdk::wait(static_cast<u64>(child), status) && status.outcome == process_outcome::exited && !status.code,
         "wait-child", status.code);
}
void settled(u64 processes, u64 pages) {
    const u64 end = now() + 2'000'000'000;
    for (;;) {
        const auto result = snapshot();
        if (result.usage.processes == processes && result.usage.pages == pages) return;
        need(now() < end, "credits-returned", static_cast<i64>(result.usage.pages)); sdk::yield();
    }
}
void family() {
    auto cap = limits(); cap.ipc_objects = 1; cap.names = 1; cap.pipes = 1;
    need(!sdk::set_process_budget(sdk::pid(), cap), "family-set");
    const auto before = snapshot();
    pipe_handles handles{};
    need(!sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&handles)), "family-pipe");
    need(!sdk::ipc_name_publish("p1b-family"), "family-name");
    u64 notification = 0;
    need(!ipc_v1::notification_create(ipc_v1_notification_right_all, notification), "family-notification");
    const i64 child = fork_child();
    if (!child) {
        auto enlarged = cap; enlarged.processes = 4;
        need(sdk::set_process_budget(sdk::pid(), enlarged) == process_error_delegation, "cannot-widen");
        auto narrowed = cap; narrowed.processes = 2; narrowed.threads = 2;
        need(!sdk::set_process_budget(sdk::pid(), narrowed), "nested-domain");
        const i64 grandchild = fork_child();
        if (!grandchild) {
            const auto root = snapshot(before.domain_id);
            need(root.usage.processes == 3 && root.usage.threads == 3 && root.usage.pipes == 1 &&
                 root.usage.names == 1 && root.usage.ipc_objects == 1, "aggregate-attribution");
            need(sdk::syscall(sys_process_fork_prepare) == process_error_resources, "fork-no-new-credits");
            pipe_handles denied{};
            need(sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&denied)) == process_error_resources, "pipe-tree-cap");
            need(sdk::ipc_name_publish("p1b-denied") == process_error_resources, "name-tree-cap");
            u64 endpoint = 0;
            need(ipc_v1::endpoint_create(ipc_v1_right_all, endpoint) == static_cast<i64>(ipc_v1_error::resources), "ipc-tree-cap");
            process_budget_snapshot untouched{}; untouched.pid = 0xfeed;
            need(sdk::query_process_budget(sdk::pid(), untouched, ~u64{0}) == process_error_denied &&
                 untouched.pid == 0xfeed, "foreign-domain-output-preserved");
            sdk::exit(0);
        }
        wait_child(grandchild); sdk::exit(0);
    }
    wait_child(child); settled(1, before.usage.pages);
    need(!sdk::syscall(sys_pipe_close, handles.read_token) && !sdk::syscall(sys_pipe_close, handles.write_token), "pipe-close");
    need(!sdk::ipc_name_unpublish("p1b-family") && !ipc_v1::notification_close(notification), "object-close");
    const auto after = snapshot();
    need(after.domain_id == before.domain_id && !after.usage.pipes && !after.usage.names && !after.usage.ipc_objects,
         "last-object-credits");
    for (u32 i = 0; i < 3; ++i) {
        const i64 restarted = fork_child(); if (!restarted) sdk::exit(0);
        wait_child(restarted); settled(1, before.usage.pages);
    }
}
void pages() {
    const u64 base_pages = snapshot().attributed.pages;
    auto cap = limits(2); cap.pages = base_pages + 2;
    need(!sdk::set_process_budget(sdk::pid(), cap), "pages-set");
    need(sdk::syscall(sys_process_fork_prepare) == process_error_resources, "fork-pages-preflight");
    const i64 original = sdk::syscall(sys_heap_break);
    need(original >= 0, "heap-base");
    need(sdk::syscall(sys_heap_break, static_cast<u64>(original) + 3 * 4096) == process_error_resources,
         "heap-budget");
    need(sdk::syscall(sys_heap_break) == original, "heap-unchanged");
    vm_request memory{1, sizeof(vm_request), 1, vm_exact_nonreplace, vm_arena_begin, 128 * 4096, 4096, 0, 0, 0, 0};
    need(sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)) == static_cast<i64>(vm_arena_begin), "vm-reserve");
    memory.operation = 2; memory.flags = 0; memory.alignment = 0; memory.protection = 3;
    need(sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)) == vm_error_resources, "vm-staged-budget");
    need(snapshot().usage.pages == base_pages, "vm-rollback-credit");
    memory.length = 2 * 4096;
    need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "vm-reuse-credit");
    need(snapshot().usage.pages == base_pages + 2, "vm-published-charge");
    memory.operation = 5; memory.protection = 0; memory.length = 128 * 4096;
    need(!sdk::syscall(sys_vm, reinterpret_cast<u64>(&memory)), "vm-unmap");
    settled(1, base_pages);
    u64 grant = 0, size = 0;
    need(ipc_v1::grant_create(0, 3 * 4096, ipc_v1_grant_right_all, grant, size) ==
         static_cast<i64>(ipc_v1_error::resources), "grant-page-cap");
    need(!ipc_v1::grant_create(0, 2 * 4096, ipc_v1_grant_right_all, grant, size), "grant-pages");
    need(snapshot().usage.pages == base_pages + 2, "grant-charge");
    need(!ipc_v1::grant_close(grant), "grant-close"); settled(1, base_pages);
}
void ipc_objects() {
    auto cap = limits(2); cap.ipc_objects = 1;
    need(!sdk::set_process_budget(sdk::pid(), cap), "ipc-set");
    for (u32 mode = 0; mode < 4; ++mode) {
        u64 object = 0, bytes = 0, denied = 0;
        const i64 created = mode == 0 ? ipc_v1::endpoint_create(ipc_v1_right_all, object) :
            mode == 1 ? ipc_v1::notification_create(ipc_v1_notification_right_all, object) :
            mode == 2 ? ipc_v1::wait_set_create(ipc_v1_wait_set_right_all, object) :
            ipc_v1::grant_create(0, 4096, ipc_v1_grant_right_all, object, bytes);
        need(!created && snapshot().usage.ipc_objects == 1, "ipc-object-charged", created);
        need(ipc_v1::notification_create(ipc_v1_notification_right_all, denied) ==
             static_cast<i64>(ipc_v1_error::resources), "ipc-shared-credit");
        const i64 closed = mode == 0 ? ipc_v1::endpoint_close(object) :
            mode == 1 ? ipc_v1::notification_close(object) :
            mode == 2 ? ipc_v1::wait_set_close(object) : ipc_v1::grant_close(object);
        need(!closed && !snapshot().usage.ipc_objects, "ipc-object-reclaimed", closed);
    }
}
void retained_alias() {
    const u64 parent = sdk::pid(), base_pages = snapshot().attributed.pages;
    auto cap = limits(2); cap.ipc_objects = 1;
    need(!sdk::set_process_budget(parent, cap), "alias-set");
    pipe_handles pipe{};
    need(!sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&pipe)), "alias-pipe");
    const i64 child = fork_child();
    if (!child) {
        u64 grant = 0, length = 0, delegated = 0;
        need(!ipc_v1::grant_create(0, 4096, ipc_v1_grant_right_all, grant, length), "alias-create");
        need(!ipc_v1::grant_delegate(grant, parent, ipc_v1_grant_right_all, delegated), "alias-delegate");
        need(sdk::syscall(sys_pipe_write, pipe.write_token, reinterpret_cast<u64>(&delegated), sizeof(delegated)) ==
             sizeof(delegated), "alias-send");
        sdk::exit(0);
    }
    u64 alias = 0;
    const u64 end = now() + 2'000'000'000;
    for (;;) {
        const i64 read = sdk::syscall(sys_pipe_read, pipe.read_token, reinterpret_cast<u64>(&alias), sizeof(alias));
        if (read == sizeof(alias)) break;
        need(read == process_error_would_block && now() < end, "alias-receive", read); sdk::yield();
    }
    wait_child(child);
    const auto retained = snapshot();
    need(retained.usage.processes == 1 && retained.usage.ipc_objects == 1 && !retained.attributed.ipc_objects &&
         retained.usage.pages == base_pages + 1, "creator-exit-retains-object-and-backing");
    u64 denied = 0;
    need(ipc_v1::endpoint_create(ipc_v1_right_all, denied) == static_cast<i64>(ipc_v1_error::resources),
         "alias-retains-credit");
    need(!ipc_v1::grant_close(alias), "last-alias-close");
    need(!snapshot().usage.ipc_objects, "alias-object-credit-returned");
    need(!sdk::syscall(sys_pipe_close, pipe.read_token) && !sdk::syscall(sys_pipe_close, pipe.write_token), "alias-pipe-close");
    settled(1, base_pages);
}
dynamic::launch_policy policy{};
u32 worker_finished = 0;
i64 worker_result = 0;
void prepare_policy(const char* path) {
    policy = {}; policy.count = 1; policy.sequence = 1; policy.sdk_sha256[0] = 1;
    policy.roots[0].root.id = 1; policy.roots[0].root.sha256[0] = 2;
    u32 i = 0; do { policy.roots[0].manifest[i] = path[i]; } while (path[i++]);
}
extern "C" [[noreturn]] void budget_worker_dispatch() {
    worker_result = static_cast<i64>(dynamic::configure(policy, now() + 500'000'000));
    __atomic_store_n(&worker_finished, 1, __ATOMIC_RELEASE);
    need(sdk::syscall(sys_thread_begin_exit) >= 0, "thread-begin-exit");
    (void)sdk::syscall(sys_thread_exit, 0); for (;;) __asm__ volatile("ud2");
}
extern "C" void budget_worker_enter();
__asm__(".text\n.globl budget_worker_enter\nbudget_worker_enter:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\ncall budget_worker_dispatch\nud2\n");
void unknown(const char* path, bool close, bool concurrent) {
    prepare_policy(path);
    if (concurrent) {
        auto cap = limits(1); cap.threads = 2; cap.pages += 64;
        need(!sdk::set_process_budget(sdk::pid(), cap), "thread-set");
        thread_header profile{1, sizeof(thread_header), 0};
        need(!sdk::syscall(sys_thread_profile, reinterpret_cast<u64>(&profile)), "thread-profile");
        thread_prepare_request request{{1, sizeof(thread_prepare_request), 0}, thread_stack_min, 16, 0};
        thread_reservation reserved{};
        need(!sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&reserved)), "thread-prepare");
        thread_start_request start{{1, sizeof(thread_start_request), 0}, reserved.tid,
            reinterpret_cast<u64>(&budget_worker_enter), 0, reserved.stack_top, reserved.tls_begin};
        need(!sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start)), "thread-start");
        const u64 end = now() + 1'000'000'000;
        bool contended = false;
        while (!__atomic_load_n(&worker_finished, __ATOMIC_ACQUIRE) && now() < end) {
            dynamic::controller_snapshot observed{}; observed.owner_pid = 0xbeef;
            if (dynamic::inspect_controller(observed) == dynamic::error::state) {
                need(observed.owner_pid == 0xbeef, "busy-output-preserved");
                need(dynamic::configure(policy, now() + 1'000'000'000) == dynamic::error::state, "controller-busy");
                thread_reservation denied{};
                need(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&denied)) ==
                     process_error_resources, "thread-tree-cap");
                contended = true; break;
            }
            sdk::yield();
        }
        need(contended, "real-controller-contention");
        u64 result = 1;
        thread_join_options join{{1, sizeof(thread_join_options), 0}, end, thread_join_mode::deadline};
        need(!sdk::syscall(sys_thread_join, reserved.tid, reinterpret_cast<u64>(&result), reinterpret_cast<u64>(&join)) &&
             !result && worker_result == static_cast<i64>(dynamic::error::io), "thread-join");
        need(snapshot().usage.threads == 1, "thread-credit-return");
    } else need(dynamic::configure(policy, now() + 250'000'000) == dynamic::error::io, "unknown-result");
    dynamic::controller_snapshot observed{};
    need(dynamic::inspect_controller(observed) == dynamic::error::none, "quarantine-inspect");
    need(observed.owner_pid == sdk::pid() && observed.quarantine_owner_pid == sdk::pid() &&
         observed.native_error == file::transport_timeout && observed.operation_sequence &&
         (observed.flags & (dynamic::controller_quarantined | dynamic::controller_uncertain)) ==
             (dynamic::controller_quarantined | dynamic::controller_uncertain), "quarantine-identity");
    need(observed.operation == (close ? dynamic::controller_operation::close : dynamic::controller_operation::open) &&
         (close ? observed.token && observed.retained_tokens : !observed.token &&
             (observed.flags & dynamic::controller_unknown_open)), "quarantine-operation");
    for (u32 i = 0; i < 3; ++i)
        need(dynamic::configure(policy, now() + 1'000'000'000) == dynamic::error::state, "no-configure-replay");
    file::client fresh; need(fresh.set_deadline(now() + 1'000'000'000) && fresh.init(), "same-session-reinit");
    need(fresh.ping() == static_cast<i64>(file::status::io), "reinit-cannot-clear-unknown");
    dynamic::controller_snapshot again{};
    need(dynamic::inspect_controller(again) == dynamic::error::none &&
         again.operation_sequence == observed.operation_sequence && again.token == observed.token,
         "first-failure-retained");
    sdk::print("P1B_QUARANTINED pid="); sdk::decimal(sdk::pid()); sdk::print(" op=");
    sdk::decimal(static_cast<u32>(observed.operation)); sdk::print("\n");
    pause(3'000'000'000);
}
void fresh() {
    file::client files; need(files.set_deadline(now() + 1'000'000'000) && files.init() && !files.ping(), "unrelated-files");
    u32 handle = 0, size = 0, version = 0;
    need(!files.open("/p1b_good.bin", file::read_only, handle, size, version) && size && !files.close(handle), "unrelated-open-close");
    auto cap = limits(1); need(!sdk::set_process_budget(sdk::pid(), cap), "unrelated-budget");
    pipe_handles pipe{};
    need(!sdk::syscall(sys_pipe_create, reinterpret_cast<u64>(&pipe)) &&
         !sdk::syscall(sys_pipe_close, pipe.read_token) && !sdk::syscall(sys_pipe_close, pipe.write_token), "unrelated-pipe");
}
void decimal_text(u64 number, char (&text)[21]) {
    char reverse[20]; u32 count = 0;
    do { reverse[count++] = static_cast<char>('0' + number % 10); number /= 10; } while (number);
    for (u32 i = 0; i < count; ++i) text[i] = reverse[count - i - 1];
    text[count] = 0;
}
u64 parse(const char* value) {
    u64 result = 0;
    for (; *value; ++value) { need(*value >= '0' && *value <= '9', "decimal"); result = result * 10 + static_cast<u64>(*value - '0'); }
    return result;
}
void exec_budget() {
    auto cap = limits(2); cap.processes = 1; cap.threads = 1;
    need(!sdk::set_process_budget(sdk::pid(), cap), "exec-set");
    const auto before = snapshot();
    sdk::spawn_options options; options.replace_image = true;
    const char* bad[]{"missing"};
    need(sdk::spawn_file_options("/bin/no-p1b.elf", 1, bad, options) < 0, "failed-exec");
    need(snapshot().domain_id == before.domain_id && snapshot().usage.pages == before.usage.pages, "failed-exec-keeps-budget");
    char pid[21], domain[21], generation[21];
    decimal_text(sdk::pid(), pid); decimal_text(before.domain_id, domain); decimal_text(before.image_generation, generation);
    const char* argv[]{"budget", "after_exec", pid, domain, generation};
    const i64 result = sdk::spawn_file_options("/bin/budget.elf", 5, argv, options);
    fail("successful-exec-returned", result);
}
}
extern "C" int xos_user_main(const xos::startup_info* startup) {
    const auto argv = reinterpret_cast<const char* const*>(startup->argv);
    if (startup->argc == 5 && sdk::equal(argv[1], "after_exec")) {
        const auto state = snapshot();
        need(state.pid == parse(argv[2]) && state.domain_id == parse(argv[3]) &&
             state.image_generation == parse(argv[4]) + 1 && state.usage.processes == 1 &&
             state.usage.threads == 1 && state.usage.pages == state.attributed.pages, "exec-inherits-budget");
        sdk::print("P1B_PASS exec\n"); return 0;
    }
    need(startup->argc == 2, "arguments");
    if (sdk::equal(argv[1], "family")) family();
    else if (sdk::equal(argv[1], "pages")) pages();
    else if (sdk::equal(argv[1], "ipc")) ipc_objects();
    else if (sdk::equal(argv[1], "unknown_open")) unknown("/p1b_unknown_open.bin", false, false);
    else if (sdk::equal(argv[1], "unknown_close")) unknown("/p1b_unknown_close.bin", true, false);
    else if (sdk::equal(argv[1], "concurrent")) unknown("/p1b_unknown_open.bin", false, true);
    else if (sdk::equal(argv[1], "fresh")) fresh();
    else if (sdk::equal(argv[1], "exec")) exec_budget();
    else if (sdk::equal(argv[1], "alias")) retained_alias();
    else fail("unknown-mode");
    sdk::print("P1B_PASS "); sdk::print(argv[1]); sdk::print("\n"); return 0;
}
