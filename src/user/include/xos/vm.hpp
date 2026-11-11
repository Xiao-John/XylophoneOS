// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/sdk.hpp>
#include <xos/vm_abi.hpp>

namespace xos::sdk {
inline i64 vm_call(const vm_request& request) {
    return syscall(sys_vm, reinterpret_cast<u64>(&request));
}
inline i64 vm_reserve(u64 address, u64 length, u64 alignment = vm_page_size, bool exact = false) {
    const vm_request request{vm_abi_version, sizeof(vm_request), static_cast<u32>(vm_operation::reserve),
                             exact ? vm_exact_nonreplace : 0, address, length, alignment, 0, 0, 0, 0};
    return vm_call(request);
}
inline i64 vm_change(vm_operation operation, u64 address, u64 length,
                     vm_protection protection = vm_protection::none) {
    const vm_request request{vm_abi_version, sizeof(vm_request), static_cast<u32>(operation), 0,
                             address, length, 0, static_cast<u32>(protection), 0, 0, 0};
    return vm_call(request);
}
}
