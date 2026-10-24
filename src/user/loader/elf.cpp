// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/elf.hpp>

namespace xos::elf {
namespace {
u16 read16(const u8* b) { return static_cast<u16>(b[0] | (u16{b[1]} << 8)); }
u32 read32(const u8* b) { return u32{read16(b)} | (u32{read16(b + 2)} << 16); }
u64 read64(const u8* b) { return u64{read32(b)} | (u64{read32(b + 4)} << 32); }
bool range(u64 offset, u64 length, u64 size) { return offset <= size && length <= size - offset; }
bool memory_read(void* context, u64 offset, u8* destination, u32 length) {
    const auto* bytes = static_cast<const u8*>(context);
    for (u32 i = 0; i < length; ++i) { destination[i] = bytes[offset + i]; }
    return true;
}
}
error inspect_reader(read_exact_fn read_exact, void* context, u64 size, u16 machine,
                     load_plan& result) {
    result = load_plan{};
    if (read_exact == nullptr || size < 64) { return error::header; }
    u8 header[64]{};
    if (!read_exact(context, 0, header, sizeof(header))) { return error::io; }
    if (read32(header) != 0x464c457f || header[4] != 2 || header[5] != 1 ||
        header[6] != 1 || read16(header + 52) != 64 || read32(header + 20) != 1) {
        return error::header;
    }
    if (read16(header + 16) != 2 || read16(header + 18) != machine ||
        (header[7] != 0 && header[7] != 3) || header[8] != 0 || read32(header + 48) != 0) {
        return error::target;
    }
    const u64 phoff = read64(header + 32);
    const u32 phcount = read16(header + 56);
    if (read16(header + 54) != 56 || phcount == 0 || phcount > 32 ||
        phoff < 64 || !range(phoff, u64{phcount} * 56, size)) { return error::bounds; }
    u8 phdrs[32 * 56]{};
    if (!read_exact(context, phoff, phdrs, phcount * 56)) { return error::io; }
    result.entry = read64(header + 24);
    bool entry_found = false;
    for (u32 i = 0; i < phcount; ++i) {
        const auto* p = phdrs + u64{i} * 56;
        const u32 kind = read32(p), flags = read32(p + 4);
        if (kind == 7) {
            if (read64(p + 32) == 0 && read64(p + 40) == 0) { continue; }
            if (result.tls.present || (flags != map_read && flags != (map_read | map_write))) {
                return error::unsupported;
            }
            auto& tls = result.tls;
            tls = {true, read64(p + 8), read64(p + 16), read64(p + 32),
                   read64(p + 40), read64(p + 48)};
            if (tls.file_bytes > tls.memory_bytes || !range(tls.offset, tls.file_bytes, size) ||
                tls.address < process_user_begin || tls.address >= process_image_end ||
                tls.memory_bytes > process_image_end - tls.address) { return error::bounds; }
            if (tls.memory_bytes > process_tls_max_bytes) { return error::too_large; }
            if (tls.alignment == 0) { tls.alignment = 1; }
            if (tls.alignment > process_tls_max_alignment ||
                (tls.alignment & (tls.alignment - 1)) != 0 ||
                (tls.address & (tls.alignment - 1)) != 0 ||
                (tls.offset & (tls.alignment - 1)) != 0) { return error::alignment; }
            continue;
        }
        if (kind != 1) {
            // No interpreter, dynamic tables, relocation mechanism or executable stack.
            if (kind == 0 || kind == 4 || kind == 6 || kind == 0x6474e552) { continue; }
            if (kind == 0x6474e551 && (flags & 1) == 0) { continue; }
            return error::unsupported;
        }
        const u64 offset = read64(p + 8), address = read64(p + 16);
        const u64 file_bytes = read64(p + 32), memory_bytes = read64(p + 40);
        const u64 alignment = read64(p + 48);
        if (file_bytes == 0 && memory_bytes == 0) { continue; }
        if (file_bytes > memory_bytes || !range(offset, file_bytes, size) ||
            address < process_user_begin || address >= process_image_end ||
            memory_bytes > process_image_end - address) { return error::bounds; }
        if (alignment > 1 && ((alignment & (alignment - 1)) != 0 ||
            (address & (alignment - 1)) != (offset & (alignment - 1)))) {
            return error::alignment;
        }
        if ((address & 4095) != (offset & 4095)) { return error::alignment; }
        if ((flags & ~u32{7}) != 0 || (flags & map_read) == 0 || (flags & 3) == 3) {
            return error::permissions;
        }
        if (memory_bytes == 0) { continue; }
        if (result.count == 8) { return error::too_large; }
        const u64 first = address & ~u64{4095};
        const u64 end = (address + memory_bytes + 4095) & ~u64{4095};
        for (u32 j = 0; j < result.count; ++j) {
            const auto& old = result.segments[j];
            const u64 old_first = old.address & ~u64{4095};
            const u64 old_end = (old.address + old.memory_bytes + 4095) & ~u64{4095};
            if (first < old_end && old_first < end) { return error::overlap; }
        }
        if (first < process_heap_end && process_tls_begin < end) { return error::bounds; }
        const u64 pages = (end - first) / 4096;
        if (pages > process_max_pages - process_reserved_pages - result.pages) { return error::too_large; }
        result.pages += static_cast<u32>(pages);
        result.segments[result.count++] = {offset, address, file_bytes, memory_bytes, flags};
        if ((flags & map_execute) != 0 && result.entry >= address &&
            result.entry - address < file_bytes) { entry_found = true; }
    }
    if (result.tls.present && result.tls.file_bytes != 0) {
        // The initialized template must name the same bytes as a readable LOAD.
        bool contained = false;
        const auto& tls = result.tls;
        for (u32 i = 0; i < result.count; ++i) {
            const auto& load = result.segments[i];
            if (tls.offset >= load.offset && tls.file_bytes <= load.file_bytes &&
                tls.offset - load.offset <= load.file_bytes - tls.file_bytes &&
                tls.address >= load.address &&
                tls.address - load.address == tls.offset - load.offset) { contained = true; }
        }
        if (!contained) { return error::bounds; }
    }
    return result.count != 0 && entry_found ? error::none : error::entry;
}
error inspect(const u8* bytes, u64 size, u16 machine, load_plan& result) {
    if (bytes == nullptr) { result = load_plan{}; return error::header; }
    return inspect_reader(memory_read, const_cast<u8*>(bytes), size, machine, result);
}
const char* error_name(error value) {
    switch (value) {
    case error::none: return "ok";
    case error::header: return "header";
    case error::target: return "target";
    case error::unsupported: return "unsupported";
    case error::bounds: return "bounds";
    case error::alignment: return "alignment";
    case error::permissions: return "permissions";
    case error::overlap: return "overlap";
    case error::entry: return "entry";
    case error::too_large: return "too_large";
    case error::io: return "io";
    }
    return "unknown";
}
}
