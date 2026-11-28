// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/dynamic.hpp>

namespace xos::dynamic {
inline constexpr u32 elf_load_limit = 64, elf_version_limit = 128;
struct elf_version {
    u32 hash;
    u16 index, flags;
    bool definition;
    char name[128], provider[128];
};
struct elf_image {
    elf::segment loads[elf_load_limit];
    u32 load_count, phnum, symbol_count, relocation_count, version_count;
    u64 entry, phoff, phaddr, span, tls_address, tls_bytes, tls_align;
    elf_version versions[elf_version_limit];
};
// All metadata is read from the same readonly OFD used for digest verification
// and eventual mapping. No pathname resolution or ELF execution occurs here.
error inspect_elf(elf::read_exact_fn read, void* context,
                  const generation& closure, u32 index, elf_image& output);
error check_versions(const generation& closure, const elf_image* images);
}
