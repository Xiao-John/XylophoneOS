#include <xos/format.hpp>
#include <xos/memory.hpp>
#include "build_info.hpp"

namespace xos {
#if XOS_COW1_PROBE
bool cow1_self_check();
#endif
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

bool vm_page_check() {
    constexpr u64 address=0x100000000000ull;
    const auto baseline=memory_status();
    const auto user_baseline=user_pages_status();
    for (i64 fail=0;fail<3;++fail) {
        const u64 space=arch::create_address_space();
        if (!space) return false;
        const auto before=memory_status();
        memory_self_test_fail_after(fail);
        const auto result=vm_prepare_page_in(space,address);
        memory_self_test_fail_after(-1);
        const auto after=memory_status();
        (void)arch::destroy_address_space(space);
        if (result!=memory_result::out_of_memory || before.free_pages!=after.free_pages ||
            before.allocated_pages!=after.allocated_pages) return false;
    }
    const u64 space=arch::create_address_space();
    if (!space) return false;
    u64 physical=0, found=0; vm_page_protection protection{}; page_permissions hardware{};
    bool owned=false, installed=false;
    bool ok=allocate_user_page(&physical)==memory_result::none;
    if (ok) { owned=true; *reinterpret_cast<u64*>(physical)=check_pattern; }
    if (ok) ok=vm_prepare_page_in(space,address)==memory_result::none;
    if (ok) { installed=vm_install_page_in(space,address,physical,vm_page_protection::none)==memory_result::none; ok=installed; }
    if (ok) ok=vm_lookup_page_in(space,address,&found,&protection)==memory_result::none &&
        found==physical && protection==vm_page_protection::none &&
        query_page_in(space,address,&found,&hardware)==memory_result::not_mapped &&
        map_page_in(space,address,physical,{true,false,true})==memory_result::already_mapped;
    if (ok) ok=vm_protect_page_in(space,address,vm_page_protection::read_write)==memory_result::none &&
        query_page_in(space,address,&found,&hardware)==memory_result::none && hardware.user &&
        hardware.writable && !hardware.executable && *reinterpret_cast<u64*>(found)==check_pattern;
    if (ok) ok=vm_protect_page_in(space,address,vm_page_protection::read_execute)==memory_result::none &&
        query_page_in(space,address,&found,&hardware)==memory_result::none && !hardware.writable && hardware.executable;
    if (ok) ok=vm_protect_page_in(space,address,vm_page_protection::none)==memory_result::none &&
        vm_remove_page_in(space,address,&found)==memory_result::none && found==physical;
    if (ok) { installed=false; ok=release_user_page(physical)==memory_result::none; owned=false; }
    if (!installed && owned) (void)release_user_page(physical);
    (void)arch::destroy_address_space(space);
    const auto after=memory_status(); const auto users=user_pages_status();
    return ok && baseline.free_pages==after.free_pages && baseline.allocated_pages==after.allocated_pages &&
        user_baseline.unique_pages==users.unique_pages && user_baseline.references==users.references;
}

bool vm_batch_copy_check() {
    const auto before=memory_status();
    const auto users_before=user_pages_status();
    const u64 source=arch::create_address_space(), destination=arch::create_address_space();
    bool ok=source && destination;
    constexpr u64 address=0x100000000000ull;
    for (u32 i=0;ok && i<33;++i) {
        u64 physical=0;
        ok=allocate_user_page(&physical)==memory_result::none;
        if (!ok) break;
        *reinterpret_cast<u64*>(physical)=check_pattern+i;
        const u64 current=address+u64{i}*page_size;
        if (vm_prepare_page_in(source,current)!=memory_result::none ||
            vm_install_page_in(source,current,physical,i==16 ? vm_page_protection::none :
                               vm_page_protection::read_write)!=memory_result::none) {
            (void)release_user_page(physical);ok=false;
        }
    }
    u64 cursor=0x40000000ull;u32 copied=0;
    for(u32 i=0;ok && cursor!=(u64{1}<<47) && i<128;++i)
        ok=copy_user_pages_batch(source,destination,33,&copied,&cursor,32)==memory_result::none;
    ok=ok && cursor==(u64{1}<<47) && copied==33;
    for(u32 i=0;ok && i<33;++i) {
        u64 original=0, clone=0;vm_page_protection a{},b{};
        const u64 current=address+u64{i}*page_size;
        ok=vm_lookup_page_in(source,current,&original,&a)==memory_result::none &&
           vm_lookup_page_in(destination,current,&clone,&b)==memory_result::none &&
           original!=clone && a==b && *reinterpret_cast<u64*>(clone)==check_pattern+i;
    }
    u64 release_cursor=0x40000000ull;u32 released=0;
    for(u32 i=0;ok && release_cursor!=(u64{1}<<47) && i<128;++i)
        ok=release_user_pages_batch(destination,&release_cursor,&released,32)==memory_result::none;
    ok=ok && release_cursor==(u64{1}<<47) && released==33;
    if(source) (void)arch::destroy_address_space(source);
    if(destination) (void)arch::destroy_address_space(destination);
    const auto after=memory_status();const auto users_after=user_pages_status();
    return ok && before.free_pages==after.free_pages && before.allocated_pages==after.allocated_pages &&
           users_before.unique_pages==users_after.unique_pages && users_before.references==users_after.references;
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
    if (!vm_page_check()) { report("fail", "vm_page"); return false; }
    if (!vm_batch_copy_check()) { report("fail", "vm_batch_copy"); return false; }
#if XOS_COW1_PROBE
    if (!cow1_self_check()) { report("fail", "cow1_page_tables"); return false; }
#endif
    format::text("[vm] event=self_check result=pass address=");
    format::hex(check_virtual);
    format::text(" physical=");
    format::hex(physical);
    format::text("\r\n");
    return true;
}
}
