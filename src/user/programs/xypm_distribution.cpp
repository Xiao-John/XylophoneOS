// SPDX-License-Identifier: Apache-2.0
#include "xypm_distribution.hpp"
#include "xypm_repository_io.hpp"

namespace xypm_distribution {
namespace {
using namespace xypm_native;
xos::dynamic::elf_image images[xos::dynamic::generation_max_objects];

void unhex(const char* text, xos::u8 output[32]) {
    for (unsigned i = 0; i < 32; ++i) {
        auto nibble = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        output[i] = static_cast<xos::u8>((nibble(text[i * 2]) << 4) | nibble(text[i * 2 + 1]));
    }
}
void named_path(const char* directory, const char* name, char (&output)[256]) {
    require(xypm_repository::absolute_path(directory, 186), "invalid authenticated repository path");
    const int count = std::snprintf(output, sizeof(output), "%s%s%s", directory,
                                    directory[1] ? "/" : "", name);
    require(count > 0 && static_cast<size_t>(count) < sizeof(output), "repository path too long");
}
size_t read_small(const char* path, void* output, size_t limit, bool (*path_check)(const char*)) {
    const uint64_t length = xypm_repository::open_regular(path, path_check);
    require(length <= limit, "authenticated repository record exceeds bound");
    require(std::fread(output, 1, static_cast<size_t>(length), xypm_repository::opened_file) == length &&
            std::fgetc(xypm_repository::opened_file) == EOF && !std::ferror(xypm_repository::opened_file),
            "authenticated repository record changed or was unreadable");
    const int closed = std::fclose(xypm_repository::opened_file);
    xypm_repository::opened_file = nullptr;
    require(closed == 0, "cannot close authenticated repository record");
    return static_cast<size_t>(length);
}
struct view { const xos::u8* bytes; size_t length; };
bool memory_read(void* context, xos::u64 offset, xos::u8* destination, xos::u32 length) {
    const auto& source = *static_cast<view*>(context);
    if (offset > source.length || length > source.length - offset) return false;
    std::memcpy(destination, source.bytes + offset, length);
    return true;
}
struct payload { FILE* file; uint64_t base, length; };
bool payload_read(void* context, xos::u64 offset, xos::u8* destination, xos::u32 length) {
    const auto& source = *static_cast<payload*>(context);
    return elf_read_at(source.file, source.base, source.length, offset, destination, length);
}
void permitted_object_path(const xos::dynamic::generation_object& object, unsigned index) {
    if (index == 1) return; // validate_generation enforces the fixed ABI interpreter path.
    char digest[65], expected[128];
    hex_digest(object.sha256, digest);
    const int size = std::snprintf(expected, sizeof(expected), "/usr/lib/xos/objects/%s.elf", digest);
    require(size > 0 && static_cast<size_t>(size) < sizeof(expected) &&
            !std::strcmp(object.path, expected), "generation object is not content-addressed");
}
}

void cleanup() { xypm_repository::cleanup(); }

void verify(const char* repository, const char* lock,
            const xypm_repository_auth::bootstrap& trust,
            const xypm_repository_auth::checkpoint& previous,
            uint64_t trusted_unix_seconds, const xos::u8 (&sdk_identity)[32],
            bool (*canonical_path)(const char*), plan& output) {
    using namespace xypm_native;
    using namespace xos::dynamic;
    using xos::dynamic::error;
    output = {};
    cleanup();
    char path[256], release_bytes[xypm_repository_auth::release_limit];
    uint8_t signature[64];
    named_path(repository, "release.json", path);
    const size_t release_length = read_small(path, release_bytes, sizeof(release_bytes), canonical_path);
    named_path(repository, "release.sig", path);
    require(read_small(path, signature, sizeof(signature), canonical_path) == sizeof(signature),
            "invalid repository signature length");
    xypm_repository_auth::authenticate(trust, release_bytes, release_length, signature, output.authenticated);
    output.next_checkpoint = xypm_repository_auth::accept_freshness(
        trust, output.authenticated, previous, trusted_unix_seconds);
    xypm_repository::verify(repository, lock, output.authenticated.lock_sha256, canonical_path);
    const auto& selected = xypm_repository::active;
    require(!std::strcmp(selected.index_digest, output.authenticated.index_sha256),
            "signed repository index digest mismatch");
    output.package_count = selected.ordered_count;

    xos::u8 generation_bytes[sizeof(generation)]{};
    named_path(repository, "generation.bin", path);
    const size_t generation_length = read_small(path, generation_bytes, sizeof(generation_bytes), canonical_path);
    generation_root root{};
    root.id = output.authenticated.generation_id;
    unhex(output.authenticated.generation_sha256, root.sha256);
    view manifest{generation_bytes, generation_length};
    require(read_generation(memory_read, &manifest, generation_length, root, sdk_identity,
                            output.generation) == error::none, "approved generation manifest rejected");
    const int written = std::snprintf(output.manifest_path, sizeof(output.manifest_path),
        "/usr/lib/xos/generations/%llu.bin", static_cast<unsigned long long>(root.id));
    require(written > 0 && static_cast<size_t>(written) < sizeof(output.manifest_path),
            "generation manifest path exceeds bound");
    for (unsigned i = 0; i < output.generation.header.object_count; ++i)
        permitted_object_path(output.generation.objects[i], i);
    std::memset(images, 0, sizeof(images));
    // Full package verification and each object preflight use the same opened
    // package instance; a path alone never supplies approved object identity.
    for (size_t package_index = 0; package_index < selected.ordered_count; ++package_index) {
        const char* digest = field(selected.ordered[package_index], "sha256")->text;
        xypm_repository::package_path(repository, digest, path);
        const uint64_t size = xypm_repository::open_regular(path, canonical_path);
        const auto package = verify_package(xypm_repository::opened_file, size);
        selected.check_package(package_index, package, size);
        for (auto* file = field(package.manifest, "files")->child; file; file = file->next) {
            const char* relative = field(file, "path")->text;
            for (unsigned index = 0; index < output.generation.header.object_count; ++index) {
                const auto& object = output.generation.objects[index];
                if (std::strcmp(relative, object.path + 1)) continue;
                auto& source = output.sources[index];
                require(!source.package_sha256[0], "multiple packages own one generation object");
                char object_digest[65];
                hex_digest(object.sha256, object_digest);
                require(static_cast<uint64_t>(field(file, "size")->number) == object.file_bytes &&
                        !std::strcmp(field(file, "sha256")->text, object_digest),
                        "package payload differs from approved generation object");
                payload object_bytes{xypm_repository::opened_file, file->payload_offset, object.file_bytes};
                auto checked = verify_object(payload_read, &object_bytes, object);
                if (checked == error::none && index)
                    checked = inspect_elf(payload_read, &object_bytes, output.generation, index, images[index]);
                if (checked == error::none && !index) {
                    xos::elf::load_plan parsed{};
                    if (xos::elf::inspect_reader(payload_read, &object_bytes, object.file_bytes, 62, parsed)
                        != xos::elf::error::none) checked = error::header;
                }
                require(checked == error::none, "generation ELF closure preflight rejected");
                std::memcpy(source.package_sha256, digest, sizeof(source.package_sha256));
                source.payload_offset = file->payload_offset;
            }
        }
        const int closed = std::fclose(xypm_repository::opened_file);
        xypm_repository::opened_file = nullptr;
        require(closed == 0, "cannot close verified generation package");
    }
    for (unsigned i = 0; i < output.generation.header.object_count; ++i)
        require(output.sources[i].package_sha256[0], "approved generation object is missing from package closure");
    require(check_versions(output.generation, images) == error::none,
            "generation symbol version closure rejected");
}
}
