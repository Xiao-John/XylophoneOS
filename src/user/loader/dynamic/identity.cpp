// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic.hpp>

namespace xos::dynamic {
namespace {
u64 value(const u8* bytes, u32 count) {
    u64 result = 0;
    for (u32 i = 0; i < count; ++i) result |= u64{bytes[i]} << (8 * i);
    return result;
}
bool equal(const void* first, const void* second, u32 size) {
    const auto* a = static_cast<const u8*>(first);
    const auto* b = static_cast<const u8*>(second);
    u8 difference = 0;
    for (u32 i = 0; i < size; ++i) difference |= a[i] ^ b[i];
    return difference == 0;
}
bool zero(const u8* bytes, u32 count) {
    u8 sum = 0;
    for (u32 i = 0; i < count; ++i) sum |= bytes[i];
    return sum == 0;
}
bool range(u64 offset, u64 length, u64 size) { return offset <= size && length <= size - offset; }
}

bool identity_valid(const object_identity& id, object_role role, const u8 (&toolchain)[32]) {
    return id.magic == identity_magic && id.version == identity_version && id.size == sizeof(id)
        && id.role == role && static_cast<u32>(role) >= 1 && static_cast<u32>(role) <= 4
        && id.machine == 62 && id.syscall_abi == 1 && id.startup_abi == 1
        && id.libc_abi == 1 && id.thread_abi == 1 && id.tls_abi == 2
        && id.profile == profile_glibc_v1 && id.required_cpu_features == cpu_x86_64_baseline
        && !zero(toolchain, 32) && equal(id.toolchain_abi, toolchain, 32) && zero(id.reserved, 40);
}

error inspect_identity(elf::read_exact_fn read, void* context, u64 bytes, const object_identity& expected) {
    if (read == nullptr || bytes < 64 || bytes > generation_file_limit) return error::bounds;
    if (!identity_valid(expected, expected.role, expected.toolchain_abi)) return error::identity;
    u8 header[64], program[56];
    if (!read(context, 0, header, sizeof(header))) return error::io;
    constexpr u8 prefix[] = {0x7f, 'E', 'L', 'F', 2, 1, 1, 0};
    if (!equal(header, prefix, sizeof(prefix)) || !zero(header + 8, 8)
        || value(header + 18, 2) != 62 || value(header + 20, 4) != 1
        || value(header + 48, 4) != 0 || value(header + 52, 2) != 64
        || value(header + 54, 2) != 56) return error::header;
    const u64 kind = value(header + 16, 2);
    if (kind != (expected.role == object_role::bootstrap ? 2u : 3u)) return error::role;
    const u64 phoff = value(header + 32, 8), count = value(header + 56, 2);
    if (count == 0 || count > 128 || !range(phoff, count * sizeof(program), bytes)) return error::bounds;
    u64 identity_offset = 0, identity_address = 0;
    u32 identities = 0, notes = 0, interpreters = 0, dynamics = 0;
    for (u32 index = 0; index < count; ++index) {
        if (!read(context, phoff + index * sizeof(program), program, sizeof(program))) return error::io;
        const u32 type = static_cast<u32>(value(program, 4)), flags = static_cast<u32>(value(program + 4, 4));
        const u64 offset = value(program + 8, 8), address = value(program + 16, 8);
        const u64 size = value(program + 32, 8);
        if (!range(offset, size, bytes)) return error::bounds;
        if (type == 2) ++dynamics;
        if (type == 3) {
            if (++interpreters != 1 || expected.role != object_role::main || size != sizeof(interpreter_path))
                return error::interpreter;
            u8 path[sizeof(interpreter_path)];
            if (!read(context, offset, path, sizeof(path))) return error::io;
            if (!equal(path, interpreter_path, sizeof(path))) return error::interpreter;
        }
        if (type != 4) continue;
        if (++notes > 8 || size > 16384 || flags != 4) return error::bounds;
        for (u64 position = 0; position < size;) {
            u8 note[12], name[4];
            if (!range(position, sizeof(note), size)) return error::bounds;
            if (!read(context, offset + position, note, sizeof(note))) return error::io;
            const u64 name_bytes = value(note, 4), descriptor_bytes = value(note + 4, 4);
            const u64 padded_name = (name_bytes + 3) & ~u64{3};
            const u64 padded_descriptor = (descriptor_bytes + 3) & ~u64{3};
            const u64 record_bytes = sizeof(note) + padded_name + padded_descriptor;
            if (!range(position, record_bytes, size)) return error::bounds;
            if (name_bytes == 4) {
                if (!read(context, offset + position + sizeof(note), name, sizeof(name))) return error::io;
                constexpr u8 native_name[] = {'X', 'O', 'S', 0};
                if (equal(name, native_name, sizeof(name)) && value(note + 8, 4) == identity_note_type) {
                    if (++identities != 1 || descriptor_bytes != sizeof(object_identity)) return error::identity;
                    object_identity observed{};
                    identity_offset = offset + position + sizeof(note) + padded_name;
                    if (!range(address, position + sizeof(note) + padded_name, ~u64{0})) return error::bounds;
                    identity_address = address + position + sizeof(note) + padded_name;
                    if (!read(context, identity_offset, reinterpret_cast<u8*>(&observed), sizeof(observed)))
                        return error::io;
                    if (!equal(&observed, &expected, sizeof(expected))) return error::identity;
                }
            }
            position += record_bytes;
        }
    }
    if (identities != 1) return error::identity;
    if (expected.role == object_role::bootstrap) {
        if (interpreters || dynamics) return error::role;
    } else if (dynamics != 1 || interpreters != (expected.role == object_role::main ? 1u : 0u)) {
        return error::role;
    }
    bool covered = false;
    for (u32 index = 0; index < count; ++index) {
        if (!read(context, phoff + index * sizeof(program), program, sizeof(program))) return error::io;
        if (value(program, 4) != 1) continue;
        const u64 offset = value(program + 8, 8), address = value(program + 16, 8);
        const u64 file_bytes = value(program + 32, 8);
        const u64 memory_bytes = value(program + 40, 8);
        if (file_bytes > memory_bytes || memory_bytes > ~u64{0} - address
            || sizeof(expected) > ~u64{0} - identity_address) return error::bounds;
        if ((value(program + 4, 4) & 2) && address < identity_address + sizeof(expected)
            && identity_address < address + memory_bytes) return error::writable_identity;
        if (identity_offset < offset || !range(identity_offset - offset, sizeof(expected), file_bytes)) continue;
        if (value(program + 4, 4) & 2) return error::writable_identity;
        if ((value(program + 4, 4) & 4) && identity_address >= address
            && identity_address - address == identity_offset - offset) covered = true;
    }
    return covered ? error::none : error::writable_identity;
}
}
