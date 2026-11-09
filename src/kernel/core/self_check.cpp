#include <xos/format.hpp>
#include <xos/memory.hpp>

namespace xos {
namespace {
constexpr u64 check_virtual = 0x40000000ull;
constexpr u64 check_pattern = 0x1122334455667788ull;

void report(const char* result, const char* reason) {
    format::text("[vm] event=self_check result=");
    format::text(result);
    if (reason != nullptr) {
        format::text(" reason=");
        format::text(reason);
    }
    format::text("\r\n");
}
bool user_rollback_check() {
    const auto before = memory_status(); const auto users_before = user_pages_status();
    const u64 source = arch::create_address_space();
    if (!source) return false;
    constexpr u64 address = (u64{1} << 39) + page_size;
    u64 physical = 0;
    bool ok = allocate_user_page(&physical) == memory_result::none;
    bool mapped = false;
    if (ok) { mapped = map_page_in(source, address, physical, {true, false, true}) == memory_result::none; ok = mapped; }
    if (!mapped && physical) (void)release_user_page(physical);
    for (i64 fail = 0; ok && fail < 4; ++fail) {
        const auto checkpoint = memory_status(); const auto users_checkpoint = user_pages_status();
        const u64 destination = arch::create_address_space();
        if (!destination) { ok = false; break; }
        memory_self_test_fail_after(fail);
        u32 copied = 0;
        const auto result = copy_user_pages_in(source, destination, 1, &copied);
        memory_self_test_fail_after(-1);
        (void)arch::destroy_address_space(destination);
        const auto now = memory_status(); const auto users_now = user_pages_status();
        ok = result == memory_result::out_of_memory && copied == 0 &&
             now.free_pages == checkpoint.free_pages && now.allocated_pages == checkpoint.allocated_pages &&
             users_now.unique_pages == users_checkpoint.unique_pages && users_now.references == users_checkpoint.references;
    }
    memory_self_test_fail_after(-1);
    (void)arch::destroy_address_space(source);
    const auto after = memory_status(); const auto users_after = user_pages_status();
    return ok && before.free_pages == after.free_pages && before.allocated_pages == after.allocated_pages &&
        users_before.unique_pages == users_after.unique_pages && users_before.references == users_after.references;
}

bool user_ownership_check() {
    const auto before = memory_status();
    const auto ubefore = user_pages_status();
    const u64 source = arch::create_address_space();
    const u64 destination = arch::create_address_space();
    bool ok = source && destination;
    u64 physical = 0;
    constexpr u64 address = (u64{1} << 39) + (u64{2} << 30) + page_size;
    if (ok) ok = allocate_user_page(&physical) == memory_result::none;
    if (ok) ok = user_page_references(physical) == 1 && retain_user_page(physical) == memory_result::none &&
                 user_page_references(physical) == 2 && release_page(physical) == memory_result::invalid &&
                 release_user_page(physical) == memory_result::none && user_page_references(physical) == 1;
    bool mapped = false;
    if (ok) { mapped = map_page_in(source, address, physical, {true, false, true}) == memory_result::none; ok = mapped; }
    if (!mapped && physical) (void)release_user_page(physical);
    if (ok) {
        *reinterpret_cast<u64*>(physical) = check_pattern;
        u32 copied = 0;
        ok = copy_user_pages_in(source, destination, 0, &copied) == memory_result::out_of_memory && copied == 0;
        if (ok) ok = copy_user_pages_in(source, destination, 1, &copied) == memory_result::none && copied == 1;
        u64 clone = 0; page_permissions permissions{}; bool logical = false;
        if (ok) ok = query_page_in(destination, address, &clone, &permissions) == memory_result::none &&
            clone != physical && *reinterpret_cast<u64*>(clone) == check_pattern && permissions.user &&
            permissions.writable && !permissions.executable &&
            query_logical_write_in(destination, address, &logical) == memory_result::none && logical;
    }
    if (source) (void)arch::destroy_address_space(source);
    if (destination) (void)arch::destroy_address_space(destination);
    const auto after = memory_status(); const auto uafter = user_pages_status();
    return ok && before.free_pages == after.free_pages && before.allocated_pages == after.allocated_pages &&
        ubefore.unique_pages == uafter.unique_pages && ubefore.references == uafter.references;
}

}

bool memory_self_check() {
    u64 physical = 0;
    if (allocate_page(&physical) != memory_result::none) {
        report("fail", "allocate");
        return false;
    }
    const page_permissions permissions{true, false, false};
    if (map_page(check_virtual, physical, permissions) != memory_result::none) {
        (void)release_page(physical);
        report("fail", "map");
        return false;
    }
    auto* word = reinterpret_cast<volatile u64*>(check_virtual);
    *word = check_pattern;
    const bool readback = (*word == check_pattern);

    u64 queried_physical = 0;
    page_permissions queried_permissions{};
    const memory_result query = query_page(check_virtual, &queried_physical, &queried_permissions);
    const memory_result duplicate = map_page(check_virtual, physical, permissions);
    const memory_result unmapped = unmap_page(check_virtual);
    const memory_result released = release_page(physical);

    const bool ok = readback && query == memory_result::none &&
                    queried_physical == physical &&
                    queried_permissions.writable && !queried_permissions.executable &&
                    duplicate == memory_result::already_mapped &&
                    unmapped == memory_result::none && released == memory_result::none;
    if (!ok) {
        report("fail", "mismatch");
        return false;
    }
    if (!user_ownership_check()) { report("fail", "user_ownership"); return false; }
    if (!user_rollback_check()) { report("fail", "user_rollback"); return false; }
    format::text("[vm] event=self_check result=pass address=");
    format::hex(check_virtual);
    format::text(" physical=");
    format::hex(physical);
    format::text("\r\n");
    return true;
}
}
