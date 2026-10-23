#include <xos/elf.hpp>

namespace xos::elf {
namespace {
u16 read16(const u8* b) { return static_cast<u16>(b[0] | (u16{b[1]} << 8)); }
u32 read32(const u8* b) { return u32{read16(b)} | (u32{read16(b + 2)} << 16); }
u64 read64(const u8* b) { return u64{read32(b)} | (u64{read32(b + 4)} << 32); }
bool range(u64 offset, u64 length, u64 size) { return offset <= size && length <= size - offset; }
}
error inspect(const u8* bytes, u64 size, u16 machine, load_plan& result) {
    result = load_plan{};
    if (bytes == nullptr || size < 64 || read32(bytes) != 0x464c457f ||
        bytes[4] != 2 || bytes[5] != 1 || bytes[6] != 1 ||
        read16(bytes + 52) != 64 || read32(bytes + 20) != 1) { return error::header; }
    if (read16(bytes + 16) != 2 || read16(bytes + 18) != machine ||
        (bytes[7] != 0 && bytes[7] != 3) || bytes[8] != 0 || read32(bytes + 48) != 0) {
        return error::target;
    }
    const u64 phoff = read64(bytes + 32);
    const u32 phcount = read16(bytes + 56);
    if (read16(bytes + 54) != 56 || phcount == 0 || phcount > 32 ||
        phoff < 64 || !range(phoff, u64{phcount} * 56, size)) { return error::bounds; }
    result.entry = read64(bytes + 24);
    bool entry_found = false;
    for (u32 i = 0; i < phcount; ++i) {
        const auto* p = bytes + phoff + u64{i} * 56;
        const u32 kind = read32(p), flags = read32(p + 4);
        if (kind != 1) {
            // No interpreter, dynamic tables, TLS, relocation mechanism or executable stack.
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
        const u64 pages = (end - first) / 4096;
        if (pages > process_max_pages - 4 - result.pages) { return error::too_large; }
        result.pages += static_cast<u32>(pages);
        result.segments[result.count++] = {offset, address, file_bytes, memory_bytes, flags};
        if ((flags & map_execute) != 0 && result.entry >= address &&
            result.entry - address < file_bytes) { entry_found = true; }
    }
    return result.count != 0 && entry_found ? error::none : error::entry;
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
    }
    return "unknown";
}
}
