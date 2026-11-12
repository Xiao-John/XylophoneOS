// SPDX-License-Identifier: Apache-2.0
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <xos/ipc_v1.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>

using namespace xos;

namespace {
constexpr u64 grant_rights = ipc_v1_grant_right_all;
constexpr u64 grant_arena = 0x100040000000ull;
constexpr u64 shared_marker = 0x584f534950433447ull;
volatile u32 race_gate;
u64 race_handle;
u64 race_address;
i64 race_map_result;
i64 race_close_result;
u64 race_id;
volatile u32 pin_wait_entered;
i64 pin_wait_result;
u64 own_pid();

void fail(const char* label, i64 result = 0) {
    printf("[ipc-v1-grant] FAIL %s result=%lld\n", label, static_cast<long long>(result));
}

u64 parse_u64(const char* value) {
    return value ? static_cast<u64>(strtoull(value, nullptr, 10)) : 0;
}

int child_mode(u64 handle, u64 address) {
    u64 map_id = 0, length = 0;
    i64 result = static_cast<i64>(ipc_v1_error::invalid_handle);
    for (u32 attempt = 0; attempt < 200; ++attempt) {
        result = ipc_v1::grant_map(handle, address, ipc_v1_grant_access::read_write, map_id, length);
        if (result == 0) { break; }
        if (result != static_cast<i64>(ipc_v1_error::invalid_handle)) { fail("child-map", result); return 11; }
        (void)thread::sleep_until(thread::clock() + 1000000ull);
    }
    if (result != 0 || length != 8192) { fail("child-map-timeout", result); return 12; }
    auto* words = reinterpret_cast<volatile u64*>(address);
    if (words[0] != 0x1020304050607080ull || words[600] != 0) { fail("child-snapshot"); return 13; }
    words[600] = shared_marker;
    // Deliberately leave the mapping installed; successful process exit must revoke it.
    printf("[ipc-v1-grant] child-shared-write PASS\n");
    return 0;
}

bool cross_process_share_and_exit() {
    u64 source[1024]{};
    source[0] = 0x1020304050607080ull;
    u64 handle = 0, length = 0;
    if (ipc_v1::grant_create(reinterpret_cast<u64>(source), sizeof(source), grant_rights, handle, length) != 0 ||
        !handle || length != sizeof(source)) { fail("create-cross-process"); return false; }
    source[0] = 0; // Creation snapshots the caller's buffer.
    char handle_text[32]{}, address_text[32]{};
    snprintf(handle_text, sizeof(handle_text), "%llu", static_cast<unsigned long long>(handle));
    constexpr u64 child_address = grant_arena + 0x100000;
    snprintf(address_text, sizeof(address_text), "%llu", static_cast<unsigned long long>(child_address));
    const char* args[] = {"child", handle_text, address_text};
    const i64 child = sdk::spawn_file("/bin/ipc_v1_grant_probe.elf", 3, args);
    if (child <= 0) { fail("spawn-child", child); (void)ipc_v1::grant_close(handle); return false; }
    u64 child_handle = 0;
    const u32 child_rights = static_cast<u32>(ipc_v1_grant_right::read_mapping) |
        static_cast<u32>(ipc_v1_grant_right::write_mapping);
    if (ipc_v1::grant_delegate(handle, static_cast<u64>(child), child_rights, child_handle) != 0 || !child_handle) {
        fail("delegate-child"); (void)ipc_v1::grant_close(handle); return false;
    }
    process_status status{};
    if (sdk::wait(static_cast<u64>(child), status) != 0 || status.outcome != process_outcome::exited || status.code != 0) {
        fail("wait-child", status.code); (void)ipc_v1::grant_close(handle); return false;
    }
    const u64 parent_address = grant_arena + 0x200000;
    u64 map_id = 0; length = 0;
    if (ipc_v1::grant_map(handle, parent_address, ipc_v1_grant_access::read, map_id, length) != 0 ||
        length != sizeof(source) || reinterpret_cast<volatile u64*>(parent_address)[600] != shared_marker) {
        fail("cross-process-shared-visibility"); (void)ipc_v1::grant_close(handle); return false;
    }
    if (ipc_v1::grant_unmap(handle, map_id) != 0 || ipc_v1::grant_close(handle) != 0) {
        fail("cross-process-cleanup"); return false;
    }
    return true;
}

void* race_map(void*) {
    while (__atomic_load_n(&race_gate, __ATOMIC_ACQUIRE) == 0) { sdk::yield(); }
    u64 length = 0;
    race_map_result = ipc_v1::grant_map(race_handle, race_address,
        ipc_v1_grant_access::read_write, race_id, length);
    if (race_map_result == 0 && length != 4096) { race_map_result = static_cast<i64>(ipc_v1_error::state); }
    return nullptr;
}
void* race_close(void*) {
    while (__atomic_load_n(&race_gate, __ATOMIC_ACQUIRE) == 0) { sdk::yield(); }
    race_close_result = ipc_v1::grant_close(race_handle);
    return nullptr;
}

void* pinned_waiter(void* opaque) {
    const u64* values = static_cast<const u64*>(opaque);
    auto* request = reinterpret_cast<ipc_v1_notification_wait*>(values[1]);
    request->handle = values[0]; request->deadline_ns = ipc_v1_deadline_infinite;
    __atomic_store_n(&pin_wait_entered, 1u, __ATOMIC_RELEASE);
    pin_wait_result = ipc_v1::invoke(ipc_v1_action::notification_wait, *request);
    return nullptr;
}

bool pinned_revoke_is_busy() {
    u64 grant = 0, length = 0, map_id = 0;
    constexpr u64 address = grant_arena + 0x600000;
    if (ipc_v1::grant_create(0, 4096, grant_rights, grant, length) != 0 ||
        ipc_v1::grant_map(grant, address, ipc_v1_grant_access::read_write, map_id, length) != 0) {
        fail("pin-grant-setup"); return false;
    }
    u64 notification = 0;
    if (ipc_v1::notification_create(ipc_v1_notification_right_all, notification) != 0) {
        fail("pin-notification-create"); (void)ipc_v1::grant_close(grant); return false;
    }
    const u64 values[] = {notification, address};
    pin_wait_result = 0; __atomic_store_n(&pin_wait_entered, 0u, __ATOMIC_RELEASE);
    pthread_t waiter{};
    if (pthread_create(&waiter, nullptr, pinned_waiter, const_cast<u64*>(values)) != 0) {
        fail("pin-wait-thread"); (void)ipc_v1::notification_close(notification);
        (void)ipc_v1::grant_close(grant); return false;
    }
    while (__atomic_load_n(&pin_wait_entered, __ATOMIC_ACQUIRE) == 0) { sdk::yield(); }
    (void)thread::sleep_until(thread::clock() + 10000000ull);
    if (ipc_v1::grant_close(grant) != static_cast<i64>(ipc_v1_error::busy)) {
        fail("pinned-close-busy"); return false;
    }
    if (ipc_v1::notification_signal(notification) != 0 || pthread_join(waiter, nullptr) != 0 ||
        pin_wait_result != 0 || reinterpret_cast<ipc_v1_notification_wait*>(address)->bits_out != 1) {
        fail("pinned-wait-wakeup", pin_wait_result); return false;
    }
    if (ipc_v1::grant_close(grant) != 0 || ipc_v1::notification_close(notification) != 0) {
        fail("pinned-revoke-retry"); return false;
    }
    return true;
}

bool map_close_races() {
    for (u32 iteration = 0; iteration < 24; ++iteration) {
        u64 handle = 0, length = 0;
        if (ipc_v1::grant_create(0, 4096, grant_rights, handle, length) != 0 || length != 4096) {
            fail("race-create"); return false;
        }
        race_handle = handle; race_address = grant_arena + 0x400000 + u64{iteration} * 0x2000;
        race_id = 0; race_map_result = race_close_result = 0;
        __atomic_store_n(&race_gate, 0u, __ATOMIC_RELEASE);
        pthread_t mapper{}, closer{};
        if (pthread_create(&mapper, nullptr, race_map, nullptr) != 0 ||
            pthread_create(&closer, nullptr, race_close, nullptr) != 0) {
            fail("race-threads"); (void)ipc_v1::grant_close(handle); return false;
        }
        __atomic_store_n(&race_gate, 1u, __ATOMIC_RELEASE);
        if (pthread_join(mapper, nullptr) != 0 || pthread_join(closer, nullptr) != 0 || race_close_result != 0 ||
            (race_map_result != 0 && race_map_result != static_cast<i64>(ipc_v1_error::invalid_handle))) {
            fail("map-close-linearization", race_map_result ? race_map_result : race_close_result); return false;
        }
        if (race_map_result == 0 && ipc_v1::grant_unmap(handle, race_id) !=
            static_cast<i64>(ipc_v1_error::invalid_handle)) { fail("close-revokes-map"); return false; }
    }
    return true;
}

bool mapping_quota_and_aliases() {
    u64 words[1024]{}; words[0] = 0xfeedc0de12345678ull;
    u64 handle = 0, length = 0;
    if (ipc_v1::grant_create(reinterpret_cast<u64>(words), sizeof(words), grant_rights, handle, length) != 0) {
        fail("create-alias"); return false;
    }
    words[0] = 0;
    u64 first = 0, second = 0, third = 0, first_length = 0, second_length = 0, third_length = 0;
    const u64 a = grant_arena, b = grant_arena + 0x10000, c = grant_arena + 0x20000;
    if (ipc_v1::grant_map(handle, a, ipc_v1_grant_access::read_write, first, first_length) != 0 ||
        ipc_v1::grant_map(handle, b, ipc_v1_grant_access::read_write, second, second_length) != 0 ||
        reinterpret_cast<volatile u64*>(a)[0] != 0xfeedc0de12345678ull) {
        fail("alias-map-or-snapshot"); (void)ipc_v1::grant_close(handle); return false;
    }
    reinterpret_cast<volatile u64*>(a)[600] = shared_marker;
    if (reinterpret_cast<volatile u64*>(b)[600] != shared_marker) { fail("same-process-shared-alias"); }
    u64 read_handle = 0;
    if (ipc_v1::grant_delegate(handle, own_pid(), static_cast<u32>(ipc_v1_grant_right::read_mapping), read_handle) != 0 ||
        ipc_v1::grant_map(read_handle, c, ipc_v1_grant_access::read, third, third_length) != 0 ||
        reinterpret_cast<volatile u64*>(c)[600] != shared_marker ||
        ipc_v1::grant_map(read_handle, grant_arena + 0x30000, ipc_v1_grant_access::read_write,
                          length, second_length) != static_cast<i64>(ipc_v1_error::denied)) {
        fail("delegated-rights"); (void)ipc_v1::grant_close(handle); return false;
    }
    if (ipc_v1::grant_unmap(handle, first) != 0 || ipc_v1::grant_unmap(handle, second) != 0 ||
        ipc_v1::grant_unmap(handle, third) != 0) { fail("alias-unmap"); (void)ipc_v1::grant_close(handle); return false; }
    constexpr u32 mapping_limit = ipc_v1_max_grant_mappings_system;
    u64 map_ids[mapping_limit]{};
    for (u32 i = 0; i < mapping_limit; ++i) {
        u64 bytes = 0;
        const u64 address = grant_arena + 0x800000 + u64{i} * 0x2000;
        if (ipc_v1::grant_map(handle, address, ipc_v1_grant_access::read, map_ids[i], bytes) != 0) {
            fail("mapping-quota-fill", i); (void)ipc_v1::grant_close(handle); return false;
        }
    }
    u64 excess_id = 0, excess_length = 0;
    if (ipc_v1::grant_map(handle, grant_arena + 0x900000, ipc_v1_grant_access::read,
                          excess_id, excess_length) != static_cast<i64>(ipc_v1_error::resources)) {
        fail("mapping-quota"); (void)ipc_v1::grant_close(handle); return false;
    }
    if (ipc_v1::grant_close(handle) != 0) { fail("close-all-maps"); return false; }
    return ipc_v1::grant_unmap(read_handle, third) == static_cast<i64>(ipc_v1_error::invalid_handle);
}

u64 own_pid() {
    thread_info info{};
    return thread::info(info) == 0 ? info.pid : 0;
}
}

int main(int argc, char** argv) {
    if (thread::enable() != 0) { fail("thread-profile"); return 1; }
    if (argv) {
        for (int i = 0; i + 2 < argc; ++i) {
            if (argv[i] && argv[i][0] == 'c') {
                return child_mode(parse_u64(argv[i + 1]), parse_u64(argv[i + 2]));
            }
        }
    }
    ipc_v1_feature_query query{};
    if (ipc_v1::query_features(query) != 0 || query.supported_features != 0) {
        fail("feature-remains-unsupported"); return 1;
    }
    if (!cross_process_share_and_exit() || !mapping_quota_and_aliases() ||
        !pinned_revoke_is_busy() || !map_close_races()) { return 1; }
    thread_stats stats{};
    if (sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&stats)) != 0 ||
        stats.threads != 1 || stats.reserved != 0 || stats.results != 0) {
        fail("thread-resource-baseline"); return 1;
    }
    printf("[ipc-v1-grant] shared-cross-process rights-race-quota-revoke PASS\n");
    return 0;
}
