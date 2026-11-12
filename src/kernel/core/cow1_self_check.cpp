// SPDX-License-Identifier: Apache-2.0
#include "build_info.hpp"
#if XOS_COW1_PROBE
#include <xos/memory.hpp>
#include <xos/format.hpp>
#include "../arch/x86_64/cow1_probe.hpp"

namespace xos {
namespace {
bool cow1_family_check() {
    constexpr u64 address=0x40010000ull, pattern=0x5aaf0123456789abull;
    const auto before=memory_status(); const auto users_before=user_pages_status();
    u64 parent=arch::create_address_space(), child=arch::create_address_space();
    u64 grandchild=arch::create_address_space(), physical=0;
    bool ok=parent && child && grandchild;
    if (ok) ok=allocate_user_page(&physical)==memory_result::none;
    if (ok) {
        *reinterpret_cast<u64*>(physical)=pattern;
        if (map_page_in(parent,address,physical,{true,false,true})!=memory_result::none) {
            (void)release_user_page(physical); physical=0; ok=false;
        }
    }
    if (ok) ok=arch::cow1_stage_page(parent,child,address)==memory_result::none &&
               arch::cow1_publish_page(parent,child,address)==memory_result::none &&
               arch::cow1_stage_page(child,grandchild,address)==memory_result::none &&
               arch::cow1_publish_page(child,grandchild,address)==memory_result::none &&
               user_page_references(physical)==3;
    if (parent) { (void)arch::destroy_address_space(parent); parent=0; }
    if (ok) ok=user_page_references(physical)==2 &&
               arch::cow1_resolve_page(grandchild,address)==memory_result::none;
    u64 copy=0; page_permissions permissions{};
    if (ok) ok=query_page_in(grandchild,address,&copy,&permissions)==memory_result::none &&
               permissions.writable && copy!=physical && *reinterpret_cast<u64*>(copy)==pattern &&
               user_page_references(physical)==1;
    if (ok) {
        *reinterpret_cast<u64*>(copy)=pattern+1;
        ok=*reinterpret_cast<u64*>(physical)==pattern &&
           arch::cow1_resolve_page(child,address)==memory_result::none;
    }
    if (grandchild) (void)arch::destroy_address_space(grandchild);
    if (child) (void)arch::destroy_address_space(child);
    if (parent) (void)arch::destroy_address_space(parent);
    const auto after=memory_status(); const auto users_after=user_pages_status();
    return ok && before.free_pages==after.free_pages && before.allocated_pages==after.allocated_pages &&
        users_before.unique_pages==users_after.unique_pages && users_before.references==users_after.references;
}
}
bool cow1_self_check() {
    constexpr u64 rw=0x40000000ull, rx=0x40001000ull, hidden=0x100000000000ull;
    constexpr u64 pattern=0x123456789abcdef0ull;
    const auto before=memory_status(); const auto users_before=user_pages_status();
    u64 parent=arch::create_address_space(), child=arch::create_address_space();
    u64 data=0, code=0, concealed=0;
    bool ok=parent && child;
    if (ok) ok=allocate_user_page(&data)==memory_result::none;
    if (ok) {
        *reinterpret_cast<u64*>(data)=pattern;
        if (map_page_in(parent,rw,data,{true,false,true})!=memory_result::none) {
            (void)release_user_page(data); data=0; ok=false;
        }
    }
    if (ok) ok=allocate_user_page(&code)==memory_result::none;
    if (ok && map_page_in(parent,rx,code,{false,true,true})!=memory_result::none) {
        (void)release_user_page(code); code=0; ok=false;
    }
    if (ok) ok=allocate_user_page(&concealed)==memory_result::none;
    if (ok) {
        *reinterpret_cast<u64*>(concealed)=pattern+1;
        if (vm_prepare_page_in(parent,hidden)!=memory_result::none ||
            vm_install_page_in(parent,hidden,concealed,vm_page_protection::none)!=memory_result::none) {
            (void)release_user_page(concealed); concealed=0; ok=false;
        }
    }
    // Failure in any intermediate-table allocation leaves the source untouched;
    // destroying the unstarted destination reclaims its partial page tables.
    for (i64 fail=0;ok && fail<3;++fail) {
        const auto checkpoint=memory_status(); const auto refs=user_pages_status();
        const u64 trial=arch::create_address_space();
        if (!trial) { ok=false; break; }
        memory_self_test_fail_after(fail);
        const auto result=arch::cow1_stage_page(parent,trial,hidden);
        memory_self_test_fail_after(-1);
        (void)arch::destroy_address_space(trial);
        const auto after=memory_status(); const auto users=user_pages_status();
        ok=result==memory_result::out_of_memory && after.free_pages==checkpoint.free_pages &&
           users.unique_pages==refs.unique_pages && users.references==refs.references &&
           user_page_references(concealed)==1;
    }
    u64 cursor=rw; u32 staged=0, batches=0;
    while (ok && cursor!=(u64{1}<<47) && batches++<4096)
        ok=arch::cow1_stage_batch(parent,child,3,&staged,&cursor,8)==memory_result::none;
    if (ok) ok=cursor==(u64{1}<<47) && staged==3 && batches>1;
    if (ok) ok=user_page_references(data)==2 && user_page_references(code)==2 &&
               user_page_references(concealed)==2;
    cursor=rw; batches=0;
    while (ok && cursor!=(u64{1}<<47) && batches++<4096)
        ok=arch::cow1_publish_batch(parent,child,&cursor,8)==memory_result::none;
    if (ok) ok=cursor==(u64{1}<<47) && batches>1;
    u64 parent_page=0,child_page=0; page_permissions pp{},cp{};
    if (ok) ok=query_page_in(parent,rw,&parent_page,&pp)==memory_result::none &&
               query_page_in(child,rw,&child_page,&cp)==memory_result::none &&
               parent_page==child_page && !pp.writable && !cp.writable;
    if (ok) {
        memory_self_test_fail_after(0);
        const auto failure=arch::cow1_resolve_page(child,rw);
        memory_self_test_fail_after(-1);
        ok=failure==memory_result::out_of_memory && user_page_references(data)==2 &&
           *reinterpret_cast<u64*>(data)==pattern;
    }
    if (ok) ok=arch::cow1_resolve_page(child,rw)==memory_result::none &&
               query_page_in(child,rw,&child_page,&cp)==memory_result::none && cp.writable &&
               child_page!=data && *reinterpret_cast<u64*>(child_page)==pattern;
    if (ok) {
        *reinterpret_cast<u64*>(child_page)=pattern+2;
        memory_self_test_fail_after(0);
        const auto unique=arch::cow1_resolve_page(parent,rw);
        memory_self_test_fail_after(-1);
        ok=unique==memory_result::none && *reinterpret_cast<u64*>(data)==pattern;
    }
    if (ok) ok=arch::cow1_resolve_page(child,rx)==memory_result::invalid &&
               vm_protect_page_in(child,hidden,vm_page_protection::read_write)==memory_result::none &&
               query_page_in(child,hidden,&child_page,&cp)==memory_result::none && !cp.writable &&
               arch::cow1_resolve_page(child,hidden)==memory_result::none &&
               query_page_in(child,hidden,&child_page,&cp)==memory_result::none && cp.writable &&
               *reinterpret_cast<u64*>(child_page)==pattern+1;
    memory_self_test_fail_after(-1);
    if (child) (void)arch::destroy_address_space(child);
    if (parent) (void)arch::destroy_address_space(parent);
    const auto after=memory_status(); const auto users_after=user_pages_status();
    ok=ok && before.free_pages==after.free_pages && before.allocated_pages==after.allocated_pages &&
       users_before.unique_pages==users_after.unique_pages && users_before.references==users_after.references;
    if (ok) ok=cow1_family_check();
    format::text(ok ? "[cow1-probe] page_tables=pass\r\n" : "[cow1-probe] page_tables=fail\r\n");
    return ok;
}
}
#endif
