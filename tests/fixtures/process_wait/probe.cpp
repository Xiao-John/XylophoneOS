// SPDX-License-Identifier: Apache-2.0
#include <xos/file_client.hpp>
#include <xos/thread_core.hpp>
using namespace xos;

namespace {
const char* self_path = "/bin/wait_any";
void check(bool condition, const char* name) {
    if (condition) return;
    sdk::print("WAIT_ANY_FAIL "); sdk::print(name); sdk::print("\n"); sdk::exit(91);
}
void pass(const char* name) {
    sdk::print("WAIT_ANY_PASS "); sdk::print(name); sdk::print("\n");
}
u64 value(const char* text) {
    u64 result = 0;
    for (u32 i = 0; text[i] != 0; ++i) {
        check(text[i] >= '0' && text[i] <= '9' && result <= 1000000000000000ULL, "number");
        result = result * 10 + static_cast<u64>(text[i] - '0');
    }
    return result;
}
void decimal(char* output, u64 number) {
    char reverse[21]; u32 length = 0;
    do { reverse[length++] = static_cast<char>('0' + number % 10); number /= 10; } while (number != 0);
    for (u32 i = 0; i < length; ++i) output[i] = reverse[length - i - 1];
    output[length] = 0;
}
u64 child(const char* mode, u64 milliseconds, u64 code) {
    char delay[21], status[21]; decimal(delay, milliseconds); decimal(status, code);
    const char* args[] = {"wait_any", mode, delay, status};
    const i64 pid = sdk::spawn_file(self_path, 4, args);
    check(pid > 0, "spawn child"); return static_cast<u64>(pid);
}
process_status sentinel() { return {99, process_outcome::faulted, 123, 57, 4, 5, 6}; }
bool unchanged(const process_status& status) {
    return status.version == 99 && status.pid == 123 && status.code == 57 && status.vector == 4;
}
void no_child() {
    process_status status = sentinel();
    check(sdk::wait_any(status, true) == process_error_denied && unchanged(status), "empty unchanged");
}

struct waiter_input { u64 target; bool precise; i64 result; process_status status; };
waiter_input waiters[2];
u64 wait_worker(void* opaque) {
    auto& input = *static_cast<waiter_input*>(opaque);
    input.status = sentinel();
    input.result = input.precise ? sdk::wait(input.target, input.status) : sdk::wait_any(input.status);
    return 70;
}
void waiting(u32 count) {
    const u64 deadline = thread::clock() + 3000000000ULL;
    for (;;) {
        thread_stats state{};
        check(sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&state)) == 0, "thread stats");
        if (state.waiting >= count) return;
        check(thread::clock() < deadline, "wait registration deadline");
        sdk::yield();
    }
}
void race(bool precise, bool single_child) {
    const u64 first = child("child", 900, 51);
    const u64 second = single_child ? 0 : child("child", 1100, 52);
    check(thread::enable() == 0, "enable native workers");
    waiters[0] = {first, precise, 123, {}}; waiters[1] = {0, false, 123, {}};
    u64 threads[2]{};
    check(thread::create(threads[0], wait_worker, &waiters[0]) == 0, "first waiter");
    waiting(1);
    check(thread::create(threads[1], wait_worker, &waiters[1]) == 0, "second waiter");
    waiting(2);
    for (u64 tid : threads) {
        u64 result = 0; check(thread::join(tid, result) == 0 && result == 70, "join waiter");
    }
    if (single_child) {
        const u32 winner = waiters[0].result == 0 ? 0 : 1;
        const u32 loser = 1 - winner;
        check(waiters[winner].result == 0 && waiters[winner].status.pid == first &&
              waiters[winner].status.code == 51, "last child winner");
        check(waiters[loser].result == process_error_denied && unchanged(waiters[loser].status), "last child wake");
    } else {
        check(waiters[0].result == 0 && waiters[1].result == 0, "both waiters succeed");
        check(waiters[0].status.pid != waiters[1].status.pid &&
              waiters[0].status.pid + waiters[1].status.pid == first + second, "unique child IDs");
        check(waiters[0].status.code + waiters[1].status.code == 103, "both statuses");
        if (precise) check(waiters[0].status.pid == first, "precise waiter priority");
    }
    no_child();
    pass(single_child ? "last-child" : precise ? "exact-any" : "two-any");
}

int sequential() {
    no_child();
    const char name[] = "building";
    const i64 building = sdk::syscall(sys_process_create, 0, reinterpret_cast<u64>(name), 8);
    check(building > 0, "building create"); no_child();
    check(sdk::syscall(sys_process_abort, static_cast<u64>(building)) == 0, "building abort");
    const u64 pid = child("child", 600, 41);
    process_status status = sentinel();
    check(sdk::wait_any(status, true) == process_error_would_block && unchanged(status), "live nohang");
    check(sdk::syscall(sys_process_wait, pid, reinterpret_cast<u64>(&status), process_wait_any) ==
          process_error_invalid && unchanged(status), "bad any target");
    check(sdk::syscall(sys_process_wait, 0, reinterpret_cast<u64>(&status), 4) ==
          process_error_invalid && unchanged(status), "bad flags");
    check(sdk::wait_any(status) == 0 && status.version == 1 && status.pid == pid &&
          status.outcome == process_outcome::exited && status.code == 41, "blocking completion");
    no_child();
    const u64 isolated = child("isolated", 0, 45);
    const u64 sibling = child("child", 100, 46);
    process_status one{}, two{};
    check(sdk::wait_any(one) == 0 && sdk::wait_any(two) == 0 && one.pid != two.pid &&
          one.pid + two.pid == isolated + sibling && one.code + two.code == 91, "parent ownership");
    no_child(); pass("sequential"); return 0;
}

int faults() {
    const u64 killed = child("child", 10000, 1);
    const u64 faulted = child("fault", 100, 0);
    check(sdk::syscall(sys_process_cancel, killed) == 0, "cancel child");
    bool saw_killed = false, saw_faulted = false;
    for (u32 i = 0; i < 2; ++i) {
        process_status status{}; check(sdk::wait_any(status) == 0, "wait fault or kill");
        if (status.pid == killed) saw_killed = status.outcome == process_outcome::killed && status.code == -9;
        if (status.pid == faulted) saw_faulted = status.outcome == process_outcome::faulted && status.vector == 6;
    }
    check(saw_killed && saw_faulted, "fault kill identity and outcome");
    no_child(); pass("fault-kill"); return 0;
}

int fork_publication() {
    file::client files; check(files.init(), "fork files session");
    const i64 pid = sdk::syscall(sys_process_fork_prepare);
    check(pid >= 0, "fork prepare");
    if (pid == 0) return 67;
    no_child(); // The prepared continuation remains invisible until commit.
    i64 result = static_cast<i64>(file::status::would_block);
    for (u32 attempt = 0; attempt < 64 && result == static_cast<i64>(file::status::would_block); ++attempt) {
        result = files.clone_session(static_cast<u64>(pid));
        if (result == static_cast<i64>(file::status::would_block)) sdk::yield();
    }
    check(result == 0 && sdk::syscall(sys_process_fork_commit, static_cast<u64>(pid)) == 0, "fork commit");
    process_status status{};
    check(sdk::wait_any(status) == 0 && status.pid == static_cast<u64>(pid) && status.code == 67, "fork published completion");
    no_child(); pass("fork-publication"); return 0;
}

int replace() {
    (void)child("child", 300, 61); (void)child("child", 600, 62);
    char own[21]; decimal(own, sdk::pid());
    const char* args[] = {"wait_exec", own};
    startup_descriptor descriptors[3]{};
    for (u32 fd = 0; fd < 3; ++fd) descriptors[fd] = {fd, fd, 1, fd, fd == 0 ? 0U : 1U, 0};
    sdk::spawn_options options;
    options.replace_image = true; options.descriptors = descriptors; options.descriptor_count = 3;
    (void)sdk::spawn_file_options("/bin/wait_exec", 2, args, options);
    check(false, "successful exec returns"); return 92;
}
}

extern "C" int xos_user_main(const startup_info* startup) {
    check(startup != nullptr && startup->argc >= 2, "arguments");
    const auto* args = reinterpret_cast<const char* const*>(startup->argv);
    const char* mode = args[1];
    if (sdk::equal(mode, "child") || sdk::equal(mode, "fault") || sdk::equal(mode, "isolated")) {
        check(startup->argc == 4, "child arguments");
        check(thread::sleep_until(thread::clock() + value(args[2]) * 1000000) == 0, "child sleep");
        if (sdk::equal(mode, "fault")) __asm__ volatile("ud2");
        if (sdk::equal(mode, "isolated")) no_child();
        return static_cast<int>(value(args[3]));
    }
    if (sdk::equal(mode, "sequential")) return sequential();
    if (sdk::equal(mode, "fault-kill")) return faults();
    if (sdk::equal(mode, "fork")) return fork_publication();
    if (sdk::equal(mode, "exec")) return replace();
    if (sdk::equal(mode, "exact-any")) { race(true, false); return 0; }
    if (sdk::equal(mode, "two-any")) { race(false, false); return 0; }
    if (sdk::equal(mode, "last-child")) { race(false, true); return 0; }
    if (sdk::equal(mode, "orphan")) { (void)child("child", 200, 44); pass("orphan-parent"); return 0; }
    if (sdk::equal(mode, "cancel")) {
        (void)child("child", 10000, 43); sdk::print("WAIT_ANY_BLOCKED\n");
        process_status status{}; (void)sdk::wait_any(status);
        check(false, "cancel target unexpectedly resumed");
    }
    check(false, "unknown mode"); return 93;
}
