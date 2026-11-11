// SPDX-License-Identifier: Apache-2.0
#include <xos/vm.hpp>
using namespace xos;
extern "C" int xos_user_main(const startup_info*) {
    constexpr u64 base=0x100000000000ull;
    if (sdk::vm_reserve(base,vm_page_size,vm_page_size,true)!=static_cast<i64>(base)) return 1;
    if (sdk::vm_change(vm_operation::protect,base,vm_page_size,vm_protection::read_write)!=0) return 2;
    auto* word=reinterpret_cast<volatile u64*>(base);*word=0x123456789abcdef0ull;
    if (sdk::vm_change(vm_operation::protect,base,vm_page_size,vm_protection::none)!=0) return 3;
    if (sdk::vm_change(vm_operation::protect,base,vm_page_size,vm_protection::read_write)!=0 ||
        *word!=0x123456789abcdef0ull) return 4;
    if (sdk::vm_change(vm_operation::unmap,base,vm_page_size)!=0) return 5;
    vm_request private_request{1,64,0xffff,0,0,0,0,0,0,0,0};
    if (sdk::vm_call(private_request)!=vm_error_invalid) return 6;
    sdk::print("VM1_PUBLIC_PASS\n");return 0;
}
