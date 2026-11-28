// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic.hpp>
#include <xos/fault_sha256.hpp>

namespace xos::dynamic {
namespace {
bool equal(const u8* a, const u8* b, u32 size) {
    u8 difference = 0;
    for (u32 i = 0; i < size; ++i) difference |= a[i] ^ b[i];
    return difference == 0;
}
bool zero(const u8* bytes, u32 count) {
    u8 sum = 0;
    for (u32 i = 0; i < count; ++i) sum |= bytes[i];
    return sum == 0;
}
bool text_valid(const char (&text)[128], bool path, bool empty) {
    u32 length = 0;
    while (length < sizeof(text) && text[length]) ++length;
    if (length == sizeof(text) || (!length && !empty)) return false;
    if (!zero(reinterpret_cast<const u8*>(text) + length, sizeof(text) - length)) return false;
    if (!length) return true;
    if (path && (text[0] != '/' || length == 1 || text[length - 1] == '/')) return false;
    u32 component = path ? 1 : 0;
    for (u32 i = path ? 1 : 0; i <= length; ++i) {
        const char c = text[i];
        if (c == '/' || i == length) {
            if ((!path && c == '/') || i == component
                || (i - component == 1 && text[component] == '.')
                || (i - component == 2 && text[component] == '.' && text[component + 1] == '.')) return false;
            component = i + 1;
        } else if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
                     || (c >= '0' && c <= '9') || c == '_' || c == '-' || c == '.' || c == '+')) return false;
    }
    return true;
}
bool same_text(const char (&a)[128], const char (&b)[128]) {
    return equal(reinterpret_cast<const u8*>(a), reinterpret_cast<const u8*>(b), 128);
}
error visit(const generation& value, u32 index, u8 (&color)[generation_max_objects], u32 depth) {
    if (depth > generation_max_objects || color[index] == 1) return error::cycle;
    if (color[index] == 2) return error::none;
    color[index] = 1;
    const auto& item = value.objects[index];
    for (u32 edge = 0; edge < item.needed_count; ++edge) {
        const error result = visit(value, item.needed[edge], color, depth + 1);
        if (result != error::none) return result;
    }
    color[index] = 2;
    return error::none;
}
}

error validate_generation(const generation& value) {
    const auto& head = value.header;
    const bool online = head.version == generation_online_version;
    if (head.magic != generation_magic || (!online && head.version != generation_version)
        || head.object_count < 3 || head.object_count > generation_max_objects || !head.id
        || head.size != sizeof(head) + head.object_count * sizeof(generation_object)
        || (!online && head.reserved0) || head.reserved1 || zero(head.sdk_sha256, 32)
        || zero(head.toolchain_abi, 32)) return error::header;
    if (online && (!head.online_mask || (head.online_mask & 7u)
        || (head.online_mask >> head.object_count))) return error::header;
    if (!head.total_file_bytes || head.total_file_bytes > generation_bytes_limit
        || !head.mapping_budget || head.mapping_budget > generation_mapping_limit
        || !head.startup_budget_ns || head.startup_budget_ns > startup_deadline_limit_ns) return error::budget;
    u64 bytes = 0, mapped = 0;
    for (u32 index = 0; index < head.object_count; ++index) {
        const auto& item = value.objects[index];
        const object_role role = index == 0 ? object_role::bootstrap
            : index == 1 ? object_role::interpreter : index == 2 ? object_role::main : object_role::library;
        if (!identity_valid(item.identity, role, head.toolchain_abi)) return error::identity;
        if (!item.file_bytes || item.file_bytes > generation_file_limit || zero(item.sha256, 32)
            || item.file_bytes > head.total_file_bytes - bytes) return error::budget;
        bytes += item.file_bytes;
        if (!text_valid(item.path, true, false)
            || !text_valid(item.soname, false, index == 0 || index == 2)
            || ((index == 0 || index == 2) && item.soname[0])) return error::path;
        if (index == 1) {
            for (u32 i = 0; i < sizeof(interpreter_path); ++i)
                if (item.path[i] != interpreter_path[i]) return error::interpreter;
        }
        if (!zero(item.reserved, sizeof(item.reserved)) || item.needed_count > generation_max_objects
            || !zero(item.needed + item.needed_count, generation_max_objects - item.needed_count)) return error::header;
        if (index == 0) {
            if (item.bias || item.span || item.needed_count) return error::role;
        } else {
            constexpr u64 begin = generation_mapping_begin, end = generation_mapping_end;
            if (item.bias < begin || item.bias >= end || item.bias % 8192 || !item.span || item.span % 4096
                || item.span > end - item.bias || item.span > head.mapping_budget - mapped) return error::budget;
            mapped += item.span;
            if (online && (head.online_mask & (1u << index))) {
                if (online_namespace_bias > end - item.bias - item.span
                    || item.span > head.mapping_budget - mapped) return error::budget;
                mapped += item.span;
                for (u32 other = 1; other < head.object_count; ++other) {
                    const auto& candidate = value.objects[other];
                    if (candidate.bias <= ~u64{0} - candidate.span
                        && item.bias + online_namespace_bias < candidate.bias + candidate.span
                        && candidate.bias < item.bias + online_namespace_bias + item.span)
                        return error::budget;
                }
            }
        }
        u32 edges = 0;
        for (u32 edge = 0; edge < item.needed_count; ++edge) {
            const u32 other = item.needed[edge];
            if (!other || other == 2 || other >= head.object_count || other == index || (edges & (1u << other)))
                return error::dependency;
            edges |= 1u << other;
            if (online && !(head.online_mask & (1u << index))
                && (head.online_mask & (1u << other))) return error::dependency;
        }
        for (u32 previous = 0; previous < index; ++previous) {
            const auto& other = value.objects[previous];
            if (same_text(item.path, other.path) || equal(item.sha256, other.sha256, 32)
                || (item.soname[0] && same_text(item.soname, other.soname))) return error::duplicate;
            if (previous && item.bias < other.bias + other.span && other.bias < item.bias + item.span)
                return error::budget;
        }
    }
    if (bytes != head.total_file_bytes) return error::budget;
    u8 color[generation_max_objects]{};
    error result = visit(value, 1, color, 0);
    if (result == error::none) result = visit(value, 2, color, 0);
    if (result == error::none && online)
        for (u32 i = 3; i < head.object_count; ++i)
            if (head.online_mask & (1u << i)) {
                result = visit(value, i, color, 0);
                if (result != error::none) break;
            }
    if (result != error::none) return result;
    for (u32 i = 1; i < head.object_count; ++i) if (color[i] != 2) return error::dependency;
    return error::none;
}

error read_generation(elf::read_exact_fn read, void* context, u64 bytes,
                      const generation_root& root, const u8 (&expected_sdk)[32], generation& output) {
    output = {};
    if (!read || bytes < sizeof(generation_header) || bytes > sizeof(output)
        || !root.id || zero(root.sha256, 32) || zero(expected_sdk, 32)) return error::bounds;
    if (!read(context, 0, reinterpret_cast<u8*>(&output), static_cast<u32>(bytes))) {
        output = {};
        return error::io;
    }
    sha256 hash;
    hash.update(reinterpret_cast<const u8*>(&output), static_cast<u32>(bytes));
    u8 digest[32];
    hash.finish(digest);
    error result = !equal(digest, root.sha256, 32) ? error::digest
        : output.header.size != bytes ? error::bounds
        : output.header.id != root.id ? error::identity
        : !equal(output.header.sdk_sha256, expected_sdk, 32) ? error::sdk : validate_generation(output);
    if (result != error::none) output = {};
    return result;
}

error verify_object(elf::read_exact_fn read, void* context, const generation_object& expected) {
    if (!read || expected.file_bytes < 64 || expected.file_bytes > generation_file_limit
        || zero(expected.sha256, 32)) return error::bounds;
    sha256 hash;
    u8 buffer[256], digest[32];
    for (u64 offset = 0; offset < expected.file_bytes;) {
        const u32 length = expected.file_bytes - offset > sizeof(buffer) ? sizeof(buffer)
            : static_cast<u32>(expected.file_bytes - offset);
        if (!read(context, offset, buffer, length)) return error::io;
        hash.update(buffer, length);
        offset += length;
    }
    hash.finish(digest);
    if (!equal(digest, expected.sha256, 32)) return error::digest;
    return inspect_identity(read, context, expected.file_bytes, expected.identity);
}

error activation_catalog::initialize(const generation_root* roots, u32 count, u32 initial) {
    return restore(roots, count, initial, 1, 0);
}
error activation_catalog::restore(const generation_root* roots, u32 count, u32 active, u64 sequence, u32 revoked) {
    if (sequence_ || !roots || !count || count > activation_max_generations || !sequence
        || (revoked & ~((1u << count) - 1)) || (active >= count && active != activation_max_generations)
        || (active < count && (revoked & (1u << active)))
        || (active == activation_max_generations && !revoked)) return error::state;
    for (u32 i = 0; i < count; ++i) {
        if (!roots[i].id || zero(roots[i].sha256, 32)) return error::identity;
        for (u32 j = 0; j < i; ++j) {
            if (roots[j].id == roots[i].id || equal(roots[j].sha256, roots[i].sha256, 32)) return error::duplicate;
        }
    }
    for (u32 i = 0; i < count; ++i) roots_[i] = roots[i];
    count_ = count;
    active_ = active;
    sequence_ = sequence;
    revoked_ = revoked;
    return error::none;
}
error activation_catalog::capture(activation_ticket& ticket) const {
    ticket = {};
    if (!sequence_ || active_ >= count_) return error::state;
    if (revoked_ & (1u << active_)) return error::revoked;
    ticket = {roots_[active_], sequence_, active_, 0};
    return error::none;
}
error activation_catalog::admit(const activation_ticket& ticket) const {
    if (!sequence_ || !ticket.sequence || ticket.sequence > sequence_ || ticket.reserved
        || ticket.index >= count_) return error::state;
    if (revoked_ & (1u << ticket.index)) return error::revoked;
    const auto& root = roots_[ticket.index];
    return root.id == ticket.root.id && equal(root.sha256, ticket.root.sha256, 32) ? error::none : error::identity;
}
error activation_catalog::activate(u32 index, u64 expected_sequence) {
    if (!sequence_ || index >= count_ || sequence_ == ~u64{0}) return error::state;
    if (sequence_ != expected_sequence) return error::stale;
    if (revoked_ & (1u << index)) return error::revoked;
    active_ = index;
    ++sequence_;
    return error::none;
}
error activation_catalog::revoke(u32 index, u64 expected_sequence) {
    if (!sequence_ || index >= count_ || sequence_ == ~u64{0}) return error::state;
    if (sequence_ != expected_sequence) return error::stale;
    if (revoked_ & (1u << index)) return error::revoked;
    revoked_ |= 1u << index;
    if (active_ == index) active_ = activation_max_generations;
    ++sequence_;
    return error::none;
}
}
