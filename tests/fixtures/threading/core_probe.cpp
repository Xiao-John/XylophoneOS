// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
using namespace xos;
namespace {
__thread u64 tls_value = 7;
__thread u64 tls_zero;
u32 shared[2];
u32 word;
u64 stack_addresses[2];
u32* heap_word;
u64 child_pid;
u64 ids[3];
u32 final_a, final_b;
u32 fifo_count, fifo_order[3];
u64 timeout_deadline;
i64 timeout_result;
void check(bool good, const char* name) {
    if (!good) { sdk::print("[threading] FAIL "); sdk::print(name); sdk::print("\n"); sdk::exit(90); }
}
thread_stats stats() {
    thread_stats value{};
    check(sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&value)) == 0, "stats"); return value;
}
u64 worker(void* argument) {
    const u32 index = static_cast<u32>(reinterpret_cast<u64>(argument));
    thread_info info{}; thread::info(info);
    u64 local = 0;
    stack_addresses[index] = reinterpret_cast<u64>(&local);
    check(info.pid == sdk::pid() && info.tid != 0 &&
        stack_addresses[index] >= info.stack_bottom && stack_addresses[index] < info.stack_top, "stack-bounds");
    check(tls_value == 7 && tls_zero == 0, "tls-template");
    tls_value = 100 + index; tls_zero = 200 + index;
    const u64 sentinel = 0x1234567800000000ull + index;
    __asm__ volatile("movq %0, %%xmm7" : : "m"(sentinel) : "xmm7");
    const u64 deadline = thread::clock() + 100000000;
    while (thread::clock() < deadline) { __atomic_fetch_add(&shared[index], 1u, __ATOMIC_RELAXED); }
    u64 observed = 0;
    __asm__ volatile("movq %%xmm7, %0" : "=m"(observed));
    check(observed == sentinel, "fpu-isolation");
    check(__atomic_load_n(&shared[1 - index], __ATOMIC_RELAXED) != 0, "preemption-without-yield");
    check(tls_value == 100 + index && tls_zero == 200 + index, "tls-isolation");
    return 40 + index;
}
u64 waiter(void* arg) {
    auto* value = static_cast<u32*>(arg);
    while (__atomic_load_n(value, __ATOMIC_ACQUIRE) == 0) {
        const i64 r = thread::wait(value, 0);
        check(r == 0 || r == thread_value_changed, "wait-result");
    }
    return 77;
}
u64 fifo_waiter(void* raw) {
    check(thread::wait(&word, 0) == 0, "fifo-wait");
    const u32 index = __atomic_fetch_add(&fifo_count, 1u, __ATOMIC_RELAXED);
    fifo_order[index] = static_cast<u32>(reinterpret_cast<u64>(raw)); return 0;
}
u64 joiner(void*) { u64 value = 0; check(thread::join(ids[0], value) == 0 && value == 77, "claimed-join"); return value; }
u64 timed_waiter(void*) { timeout_result = thread::wait(&word, 0, timeout_deadline); return 0; }
u64 leaving_peer(void*) {
    check(sdk::syscall(sys_thread_begin_exit) == 0, "peer-begin-nonlast");
    __atomic_store_n(&final_a, 1u, __ATOMIC_RELEASE);
    for (u32 count = 0; count < 20000000; ++count) { __asm__ volatile("" : : : "memory"); }
    __atomic_store_n(&final_a, 2u, __ATOMIC_RELEASE);
    (void)sdk::syscall(sys_thread_exit, 0); sdk::exit(99);
}
u64 second_leaving_peer(void*) {
    while (__atomic_load_n(&final_a, __ATOMIC_ACQUIRE) == 0) { sdk::yield(); }
    check(sdk::syscall(sys_thread_begin_exit) == 0, "second-peer-begin");
    __atomic_store_n(&final_b, 1u, __ATOMIC_RELEASE);
    (void)sdk::syscall(sys_thread_exit, 0); sdk::exit(99);
}
u64 builder(void*) {
    const char* args[] = {"child"};
    const i64 child = sdk::spawn_file("/bin/child.elf", 1, args);
    check(child > 0, "worker-process-authority"); child_pid = static_cast<u64>(child); return 5;
}
u64 bad(void*) { *reinterpret_cast<volatile u32*>(0x12345000) = 1; return 0; }
u64 last_worker(void*) {
    thread::sleep_until(thread::clock() + 50000000);
    sdk::print("[threading] last-thread-cleanup\n"); return 0;
}
}
extern "C" int xos_user_main(const startup_info* startup) {
    const char* mode = "core";
    if (startup != nullptr && startup->argc > 1) {
        mode = reinterpret_cast<const char* const*>(startup->argv)[1];
    }
    check(thread::enable() == 0, "profile");
    if (sdk::equal(mode, "arbitration")) {
        check(thread::create(ids[0], leaving_peer, nullptr) == 0, "leaving-peer-create");
        check(thread::create(ids[1], second_leaving_peer, nullptr) == 0, "second-peer-create");
        while (__atomic_load_n(&final_b, __ATOMIC_ACQUIRE) == 0) { sdk::yield(); }
        check(sdk::syscall(sys_thread_begin_exit) == 1 && __atomic_load_n(&final_a, __ATOMIC_ACQUIRE) == 2,
              "last-exit-waits-for-leaving-peer");
        sdk::print("[threading] last-arbitration-stopped-peer=ok\n");
        (void)sdk::syscall(sys_thread_exit, 0); sdk::exit(99);
    }
    if (sdk::equal(mode, "builder")) {
        check(thread::create(ids[0], builder, nullptr) == 0, "builder-thread");
        u64 result = 0; check(thread::join(ids[0], result) == 0 && result == 5, "builder-exit");
        process_status status{};
        check(sdk::wait(child_pid, status) == 0 && status.outcome == process_outcome::exited && status.code == 42,
              "child-survives-worker-exit");
        sdk::print("[threading] worker-builder-child-survives-thread-exit=ok\n"); return 0;
    }
    if (sdk::equal(mode, "foreignwake")) {
        check(thread::wake(&word, 0xffffffffu) == 0, "cross-process-wake-denied");
        sdk::print("[threading] cross-process-same-address-private=ok\n"); return 0;
    }
    if (sdk::equal(mode, "blocked")) {
        for (u32 i = 0; i < 2; ++i) { check(thread::create(ids[i], waiter, &word) == 0, "blocked-create"); }
        thread::sleep_until(thread::clock() + 30000000);
        check(stats().waiting == 2, "two-workers-blocked-before-kill");
        sdk::print("[threading] all-blocked\n");
        (void)thread::wait(&word, 0); sdk::exit(96);
    }
    if (sdk::equal(mode, "fault")) {
        check(thread::create(ids[0], bad, nullptr) == 0, "fault-create");
        for (;;) { thread::sleep_until(thread::clock() + 100000000); }
    }
    if (sdk::equal(mode, "last")) {
        check(thread::create(ids[0], last_worker, nullptr) == 0, "last-create");
        // Last-thread arbitration must revoke an unstarted reservation too.
        thread_prepare_request pending{{1, sizeof(thread_prepare_request), 0}, thread_stack_min, 4096, 0};
        thread_reservation reservation{};
        check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&pending), reinterpret_cast<u64>(&reservation)) == 0, "last-reservation");
        thread::exit(12);
    }
    thread_prepare_request request{{1, sizeof(thread_prepare_request), 0}, thread_stack_min, 4096, 0};
    thread_reservation reservation[3]{};
    const auto baseline = stats();
    check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), 1) == thread_error_address, "bad-output");
    request.header.reserved = 1;
    check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&reservation[0])) == process_error_invalid, "reserved-field");
    request.header.reserved = 0;
    for (u32 round = 0; round < 4; ++round) {
        for (auto& r : reservation) {
            check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&r)) == 0, "prepare");
        }
        thread_reservation extra{};
        check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&extra)) == process_error_resources, "quota");
        thread_start_request start{{1, sizeof(thread_start_request), 0}, reservation[0].tid,
            reinterpret_cast<u64>(&word), 0, reservation[0].stack_top, reservation[0].tls_begin};
        check(sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start)) == process_error_invalid, "non-exec-entry");
        start.entry = reinterpret_cast<u64>(&worker); start.stack += 1;
        check(sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start)) == process_error_invalid, "bad-stack");
        start.stack -= 1; start.thread_pointer = process_heap_begin;
        check(sdk::syscall(sys_thread_start, reinterpret_cast<u64>(&start)) == process_error_invalid, "bad-tls");
        check(thread::join(thread::self(), extra.tid) == thread_error_deadlock, "self-join");
        check(thread::join(0xf0000000, extra.tid) == thread_error_not_found, "unknown-tid");
        for (auto& r : reservation) { check(sdk::syscall(sys_thread_abort, r.tid) == 0, "abort"); }
        check(stats().free_pages == baseline.free_pages && stats().threads == 1, "abort-reclaims-pages-tables-slots");
    }
    // Force a real page-quota failure after TLS and part of a stack have
    // already been mapped, then check both leaf and page-table rollback.
    const u64 fill_pages = process_max_pages - baseline.process_user_pages - 3;
    check(sdk::syscall(sys_heap_break, process_heap_begin + fill_pages * 4096) > 0, "fill-page-quota");
    const auto full = stats();
    thread_reservation failed{};
    check(sdk::syscall(sys_thread_prepare, reinterpret_cast<u64>(&request), reinterpret_cast<u64>(&failed)) == thread_error_memory,
          "partial-prepare-ENOMEM");
    check(stats().free_pages == full.free_pages && stats().process_user_pages == full.process_user_pages && stats().reserved == 0,
          "partial-prepare-full-rollback");
    check(sdk::syscall(sys_heap_break, process_heap_begin) > 0 && stats().free_pages == baseline.free_pages, "quota-pages-reclaimed");
    for (u32 i = 0; i < 2; ++i) {
        check(thread::create(ids[i], worker, reinterpret_cast<void*>(static_cast<u64>(i))) == 0, "create");
    }
    for (u32 i = 0; i < 2; ++i) {
        u64 value = 0; check(thread::join(ids[i], value) == 0 && value == 40 + i, "join-value");
        check(thread::join(ids[i], value) == thread_error_not_found, "join-once");
    }
    check(stack_addresses[0] != stack_addresses[1] && tls_value == 7 && tls_zero == 0, "main-isolation");
    check(stats().free_pages == baseline.free_pages && stats().threads == 1, "thread-reclaim");
    check(thread::wake(&word) == 0, "wake-before-wait");
    word = 1;
    check(thread::wait(&word, 0, 0) == thread_value_changed, "changed-before-timeout");
    check(thread::wait(reinterpret_cast<u32*>(1), 0) == thread_error_address, "invalid-wait");
    word = 0;
    const u64 deadline = thread::clock() + 25000000;
    check(thread::wait(&word, 0, deadline) == thread_error_timeout && thread::clock() >= deadline, "absolute-timeout");
    check(thread::create(ids[0], waiter, &word) == 0, "waiter-create");
    thread::sleep_until(thread::clock() + 30000000);
    check(stats().waiting == 1, "blocked-observable");
    word = 1; check(thread::wake(&word) == 1, "wake-count");
    u64 value = 0; check(thread::join(ids[0], value) == 0 && value == 77, "wait-join");
    check(sdk::syscall(sys_heap_break, process_heap_begin + 4096) > 0, "heap-page");
    heap_word = reinterpret_cast<u32*>(process_heap_begin); *heap_word = 0;
    check(thread::create(ids[0], waiter, heap_word) == 0, "heap-waiter");
    thread::sleep_until(thread::clock() + 30000000);
    check(sdk::syscall(sys_heap_break, process_heap_begin) == thread_error_busy, "pinned-unmap-busy");
    *heap_word = 1; check(thread::wake(heap_word) == 1, "heap-wake");
    check(thread::join(ids[0], value) == 0, "heap-join");
    check(sdk::syscall(sys_heap_break, process_heap_begin) > 0, "unpinned-unmap");
    word = 0;
    check(thread::create(ids[0], waiter, &word) == 0, "detach-create");
    check(thread::detach(ids[0]) == 0, "detach");
    check(thread::join(ids[0], value) == process_error_invalid, "detached-join");
    word = 1; thread::wake(&word);
    thread::sleep_until(thread::clock() + 40000000);
    check(stats().free_pages == baseline.free_pages && stats().threads == 1, "detach-reclaim");
    word = 0;
    for (u32 i = 0; i < 3; ++i) {
        check(thread::create(ids[i], fifo_waiter, reinterpret_cast<void*>(static_cast<u64>(i))) == 0, "fifo-create");
        thread::sleep_until(thread::clock() + 20000000);
        check(stats().waiting == i + 1, "fifo-enqueued");
    }
    for (u32 i = 0; i < 3; ++i) {
        check(thread::wake(&word) == 1, "fifo-wake");
        thread::sleep_until(thread::clock() + 20000000);
        check(fifo_count == i + 1 && fifo_order[i] == i, "fifo-order");
        check(thread::join(ids[i], value) == 0, "fifo-join");
    }
    word = 0;
    check(thread::create(ids[0], waiter, &word) == 0, "unique-target");
    check(thread::create(ids[1], joiner, nullptr) == 0, "unique-joiner");
    thread::sleep_until(thread::clock() + 30000000);
    check(stats().waiting == 2 && thread::join(ids[0], value) == process_error_invalid &&
        thread::detach(ids[0]) == process_error_invalid, "unique-join-claim");
    word = 1; thread::wake(&word);
    check(thread::join(ids[1], value) == 0 && value == 77, "unique-join-delivery");
    word = 0;
    timeout_deadline = thread::clock() + 50000000;
    check(thread::create(ids[0], timed_waiter, nullptr) == 0, "deadline-create");
    thread::sleep_until(timeout_deadline);
    check(thread::wake(&word) == 0, "same-tick-timeout-wins-once");
    check(thread::join(ids[0], value) == 0 && timeout_result == thread_error_timeout, "same-tick-result");
    timeout_deadline = thread::clock() + 50000000;
    check(thread::create(ids[0], timed_waiter, nullptr) == 0, "wake-deadline-create");
    thread::sleep_until(thread::clock() + 20000000);
    check(thread::wake(&word) == 1, "wake-before-expiry");
    thread::sleep_until(timeout_deadline + 10000000);
    check(thread::join(ids[0], value) == 0 && timeout_result == 0, "wake-not-completed-twice");
    check(stats().free_pages == baseline.free_pages && stats().threads == 1, "all-core-resources-reclaimed");
    sdk::print("[threading] shared stack tls fpu preempt prepare rollback join detach wait timeout pins=ok\n");
    return 0;
}
