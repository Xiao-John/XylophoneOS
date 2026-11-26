// SPDX-License-Identifier: Apache-2.0
#include <errno.h>
#include <xos/elf.hpp>
#include <xos/sdk.hpp>

extern "C" long __xos_inspect_image(xos::elf::read_exact_fn read, void* context, xos::u64 size) {
    xos::elf::load_plan plan{};
    const auto result = xos::elf::inspect_reader(read, context, size, xos::sdk::target_elf_machine(), plan);
    if (result == xos::elf::error::none) { return 0; }
    return result == xos::elf::error::io ? -EIO : -EACCES;
}
