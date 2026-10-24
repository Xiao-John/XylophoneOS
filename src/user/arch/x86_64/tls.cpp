// SPDX-License-Identifier: Apache-2.0
#include <xos/tls.hpp>
#include <xos/sdk.hpp>
namespace xos::sdk {
namespace {
alignas(16) u8 tls_page[4096];
u64 align_up(u64 size, u64 alignment) { return (size + alignment - 1) & ~(alignment - 1); }
}
i64 map_static_tls(const elf::load_plan& plan, elf::read_exact_fn read_exact,
                   void* context, u64 child) {
    if (!plan.tls.present) { return 0; }
    // AMD64 variant II: data precedes TP; FS:0 points to the TCB itself.
    // ELF TPOFF uses the template rounded to p_align, independently of TCB alignment.
    const auto& tls = plan.tls;
    const u64 size = align_up(tls.memory_bytes, tls.alignment);
    const u64 tp_alignment = tls.alignment < 16 ? 16 : tls.alignment;
    const u64 tp = align_up(process_tls_begin + size, tp_alignment);
    const u64 base = tp - size;
    const u64 end = align_up(tp + 16, 4096);
    const u64 pages = (end - process_tls_begin) / 4096;
    if (end > process_tls_end || pages > process_max_pages - process_reserved_pages - plan.pages) {
        return process_error_resources;
    }
    for (u64 address = process_tls_begin; address < end; address += 4096) {
        for (auto& byte : tls_page) { byte = 0; }
        const u64 start = address > base ? address : base;
        const u64 file_end = base + tls.file_bytes < address + 4096
            ? base + tls.file_bytes : address + 4096;
        if (start < file_end && !read_exact(context, tls.offset + start - base,
                                            tls_page + start - address,
                                            static_cast<u32>(file_end - start))) {
            return process_error_invalid;
        }
        if (tp >= address && tp < address + 4096) {
            for (u32 i = 0; i < 8; ++i) { tls_page[tp - address + i] = static_cast<u8>(tp >> (8 * i)); }
        }
        process_page mapping{address, reinterpret_cast<u64>(tls_page), 4096, map_read | map_write};
        const i64 result = syscall(sys_process_map, child, reinterpret_cast<u64>(&mapping));
        if (result < 0) { return result; }
    }
    return syscall(sys_process_tls, child, tp);
}
}
