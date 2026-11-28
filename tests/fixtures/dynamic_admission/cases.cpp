// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic.hpp>
#include <xos/fault_sha256.hpp>
#include "fixture.hpp"

using namespace xos;
using namespace xos::dynamic;
extern "C" void admission_check(const char*, bool);
namespace {
u8 changed[sizeof(fixture_bytes)];
generation valid{}, altered{}, decoded{};
struct memory { const u8* bytes; u64 size; };
bool read(void* raw, u64 offset, u8* destination, u32 length) {
    const auto& input = *static_cast<memory*>(raw);
    if (offset > input.size || length > input.size - offset) return false;
    for (u32 i = 0; i < length; ++i) destination[i] = input.bytes[offset + i];
    return true;
}
void copy(u8* to, const u8* from, u32 count) { for (u32 i = 0; i < count; ++i) to[i] = from[i]; }
void text(char (&to)[128], const char* from) {
    for (u32 i = 0; i < sizeof(to); ++i) to[i] = 0;
    for (u32 i = 0; from[i]; ++i) to[i] = from[i];
}
void hash(const void* data, u32 bytes, u8 (&sum)[32]) {
    sha256 sha;
    sha.update(data, bytes);
    sha.finish(sum);
}
error inspect_changed() {
    memory input{changed, sizeof(changed)};
    return inspect_identity(read, &input, input.size, fixture_identity);
}
}

extern "C" void run_admission_cases() {
    memory input{fixture_bytes, sizeof(fixture_bytes)};
    admission_check("actual_native_note", inspect_identity(read, &input, input.size, fixture_identity) == error::none);
    admission_check("object_digest_and_identity", verify_object(read, &input, fixture_object) == error::none);
    auto wrong = fixture_object;
    wrong.sha256[0] ^= 1;
    admission_check("wrong_object_digest", verify_object(read, &input, wrong) == error::digest);
    wrong = fixture_object;
    wrong.identity.toolchain_abi[0] ^= 1;
    admission_check("wrong_toolchain_identity", inspect_identity(read, &input, input.size, wrong.identity) == error::identity);
    wrong = fixture_object;
    ++wrong.identity.version;
    admission_check("unknown_identity_version", inspect_identity(read, &input, input.size, wrong.identity) == error::identity);
    copy(changed, fixture_bytes, sizeof(changed)); changed[7] = 3;
    admission_check("foreign_elf_abi", inspect_changed() == error::header);
    copy(changed, fixture_bytes, sizeof(changed)); changed[16] = 2;
    admission_check("wrong_elf_role", inspect_changed() == error::role);
    copy(changed, fixture_bytes, sizeof(changed)); changed[fixture_identity_offset] ^= 1;
    admission_check("changed_native_note", inspect_changed() == error::identity);
    copy(changed, fixture_bytes, sizeof(changed)); changed[fixture_note_header] = 0;
    admission_check("missing_native_note", inspect_changed() == error::identity);
    copy(changed, fixture_bytes, sizeof(changed));
    copy(changed + fixture_stack_header, changed + fixture_note_header, 56);
    admission_check("duplicate_native_note", inspect_changed() == error::identity);
    copy(changed, fixture_bytes, sizeof(changed)); changed[fixture_identity_load_header + 4] |= 2;
    admission_check("writable_identity", inspect_changed() == error::writable_identity);
    copy(changed, fixture_bytes, sizeof(changed)); changed[56] = 129; changed[57] = 0;
    admission_check("program_header_budget", inspect_changed() == error::bounds);
    memory short_input{fixture_bytes, 70};
    admission_check("truncated_elf", inspect_identity(read, &short_input, short_input.size, fixture_identity) == error::bounds);

    valid = {};
    valid.header = {generation_magic, generation_version, sizeof(generation_header) + 4 * sizeof(generation_object),
                    7, 4, 0, {}, {}, 4 * 4096, 3 * 8192, 30000000000ULL, 0};
    valid.header.sdk_sha256[0] = 81;
    copy(valid.header.toolchain_abi, fixture_identity.toolchain_abi, 32);
    const char* paths[] = {"/app/bootstrap", interpreter_path, "/app/main", "/lib/libsample.so"};
    for (u32 i = 0; i < 4; ++i) {
        auto& item = valid.objects[i];
        item.file_bytes = 4096;
        item.sha256[0] = static_cast<u8>(i + 1);
        item.identity = fixture_identity;
        item.identity.role = static_cast<object_role>(i + 1);
        if (i) { item.bias = 0x140000000000ULL + i * 0x100000; item.span = 8192; }
        text(item.path, paths[i]);
    }
    text(valid.objects[1].soname, "ld.so.1");
    text(valid.objects[3].soname, "libsample.so");
    valid.objects[2].needed_count = 2;
    valid.objects[2].needed[0] = 1;
    valid.objects[2].needed[1] = 3;
    admission_check("bounded_generation_graph", validate_generation(valid) == error::none);
    generation_root root{7, {}};
    hash(&valid, valid.header.size, root.sha256);
    memory manifest{reinterpret_cast<const u8*>(&valid), valid.header.size};
    admission_check("bound_generation_snapshot", read_generation(read, &manifest, manifest.size, root,
                    valid.header.sdk_sha256, decoded) == error::none && decoded.header.id == 7);
    auto bad_root = root; bad_root.sha256[0] ^= 1;
    admission_check("untrusted_generation_bytes", read_generation(read, &manifest, manifest.size, bad_root,
                    valid.header.sdk_sha256, decoded) == error::digest && decoded.header.magic == 0);
    bad_root = root; ++bad_root.id;
    admission_check("mismatched_generation_id", read_generation(read, &manifest, manifest.size, bad_root,
                    valid.header.sdk_sha256, decoded) == error::identity && decoded.header.magic == 0);
    u8 other_sdk[32]{}; other_sdk[0] = 90;
    admission_check("mixed_sdk", read_generation(read, &manifest, manifest.size, root,
                    other_sdk, decoded) == error::sdk && decoded.header.magic == 0);
    altered = valid; altered.objects[3].path[6] = '/'; altered.objects[3].path[7] = '.'; altered.objects[3].path[8] = '.'; altered.objects[3].path[9] = '/';
    admission_check("noncanonical_path", validate_generation(altered) == error::path);
    altered = valid; text(altered.objects[3].soname, "ld.so.1");
    admission_check("ambiguous_soname", validate_generation(altered) == error::duplicate);
    altered = valid; text(altered.objects[1].path, "/tmp/ld.so.1");
    admission_check("interpreter_alias_rejected", validate_generation(altered) == error::interpreter);
    altered = valid; copy(altered.objects[3].sha256, altered.objects[1].sha256, 32);
    admission_check("duplicate_object", validate_generation(altered) == error::duplicate);
    altered = valid; altered.objects[2].needed[1] = 7;
    admission_check("missing_dependency", validate_generation(altered) == error::dependency);
    altered = valid; altered.objects[1].needed_count = 1; altered.objects[1].needed[0] = 3;
    altered.objects[3].needed_count = 1; altered.objects[3].needed[0] = 1;
    admission_check("dependency_cycle", validate_generation(altered) == error::cycle);
    altered = valid; altered.objects[2].needed_count = 1; altered.objects[2].needed[1] = 0;
    admission_check("unreachable_library", validate_generation(altered) == error::dependency);
    altered = valid; altered.objects[3].bias = altered.objects[2].bias;
    admission_check("mapping_collision", validate_generation(altered) == error::budget);
    altered = valid; --altered.header.mapping_budget;
    admission_check("mapping_budget", validate_generation(altered) == error::budget);
    altered = valid; ++altered.header.startup_budget_ns;
    admission_check("startup_budget", validate_generation(altered) == error::budget);
    altered = valid; altered.objects[0].reserved[3] = 1;
    admission_check("reserved_encoding", validate_generation(altered) == error::header);
    altered = valid; altered.header.object_count = 13;
    admission_check("object_budget", validate_generation(altered) == error::header);

    generation_root roots[] = {{7, {1}}, {8, {2}}, {9, {3}}};
    activation_catalog catalog;
    activation_ticket first{}, second{}, last{};
    admission_check("activate_initial_root", catalog.initialize(roots, 3, 0) == error::none
                    && catalog.capture(first) == error::none && first.root.id == 7);
    admission_check("capture_survives_activation", catalog.activate(1, 1) == error::none
                    && catalog.admit(first) == error::none && catalog.capture(second) == error::none
                    && second.root.id == 8 && second.sequence == 2);
    admission_check("stale_activation_rejected", catalog.activate(2, 1) == error::stale && catalog.sequence() == 2);
    admission_check("explicit_preapproved_rollback", catalog.activate(0, 2) == error::none
                    && catalog.capture(last) == error::none && last.root.id == 7);
    admission_check("revocation_cancels_captured_admission", catalog.revoke(0, 3) == error::none
                    && catalog.admit(first) == error::revoked && catalog.capture(last) == error::state);
    admission_check("revoked_rollback_rejected", catalog.activate(0, 4) == error::revoked && catalog.sequence() == 4);
    admission_check("recover_approved_generation", catalog.activate(2, 4) == error::none
                    && catalog.capture(last) == error::none && last.root.id == 9);
    last.root.sha256[0] ^= 1;
    admission_check("forged_ticket_rejected", catalog.admit(last) == error::identity);
    admission_check("immutable_root_catalog", catalog.initialize(roots, 3, 0) == error::state);
}
