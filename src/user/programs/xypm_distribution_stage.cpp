// SPDX-License-Identifier: Apache-2.0
#include "xypm_distribution_stage.hpp"
#include "xypm_repository_io.hpp"
#include <xos/sdk.hpp>

namespace xypm_distribution {
namespace {
using namespace xypm_native;
using xos::u8;
using xos::u32;
using xos::u64;
using xos::i64;

void response(staging_context& state, i64 result, const char* message) {
    state.native_error = result;
    if (result == xos::file::transport_timeout || result == static_cast<i64>(xos::file::status::io))
        state.quarantined = true;
    require(result >= 0, message);
}
void checkpoint(staging_context& state) {
    ++state.checkpoints;
#ifdef XYP_TEST_FAULTS
    const char* point = std::getenv("XYP_DISTRIBUTION_STOP_AFTER");
    if (point && std::strtoul(point, nullptr, 10) == state.checkpoints) {
        std::printf("xypm-test: distribution_staging_stop=%u\n", state.checkpoints);
        std::fflush(stdout);
        xos::sdk::exit(70);
    }
#endif
}
void close(staging_context& state) {
    const i64 result = state.files.close(state.handle);
    response(state, result, "staged handle close outcome is not confirmed");
    state.handle = 0;
}
void parent_directories(staging_context& state, const char* target,
                        bool (*canonical_path)(const char*)) {
    char directory[128];
    require(std::strlen(target) < sizeof(directory), "staging path exceeds bound");
    std::strcpy(directory, target);
    for (char* cursor = directory + 1; *cursor; ++cursor) {
        if (*cursor != '/') continue;
        *cursor = 0;
        u32 size = 0, flags = 0;
        const i64 found = state.files.stat_info(directory, size, flags);
        if (found == static_cast<i64>(xos::file::status::not_found)) {
            response(state, state.files.mkdir(directory), "cannot create generation staging directory");
            checkpoint(state);
        } else {
            response(state, found, "cannot inspect generation staging directory");
            require(flags & xos::file::stat_is_directory, "generation parent is not a directory");
            require(!canonical_path || canonical_path(directory), "generation parent is not canonical");
        }
        *cursor = '/';
    }
}
void check_handle(staging_context& state, uint64_t length, const u8 expected[32]) {
    sha256 hash;
    u8 block[1024], actual[32];
    uint64_t remaining = length;
    while (remaining) {
        const u32 amount = remaining > sizeof(block) ? sizeof(block) : static_cast<u32>(remaining);
        const i64 got = state.files.read(state.handle, block, amount);
        response(state, got, "cannot read back staged object");
        require(got > 0 && static_cast<u64>(got) <= amount, "staged object ended early");
        hash.update(block, static_cast<size_t>(got));
        remaining -= static_cast<u64>(got);
    }
    const i64 eof = state.files.read(state.handle, block, 1);
    response(state, eof, "cannot read staged object boundary");
    require(eof == 0, "staged object grew during verification");
    hash.finish(actual);
    require(!std::memcmp(actual, expected, 32), "existing/staged object digest mismatch");
}
bool already_staged(staging_context& state, const char* path, uint64_t expected_size,
                    const u8 expected_hash[32], bool (*canonical_path)(const char*)) {
    u32 size = 0, version = 0;
    const i64 opened = state.files.open(path, xos::file::read_only | xos::file::open_pin,
                                       state.handle, size, version);
    if (opened == static_cast<i64>(xos::file::status::not_found)) return false;
    response(state, opened, "cannot pin existing generation object");
    require(state.handle && size == expected_size, "existing generation object size mismatch");
    require(!canonical_path || canonical_path(path), "existing generation object is not canonical");
    check_handle(state, expected_size, expected_hash);
    require(state.pin_count < xos::dynamic::generation_max_objects + 1, "generation staging pin bound exceeded");
    state.pins[state.pin_count++] = state.handle;
    state.handle = 0;
    return true;
}
void write(staging_context& state, const void* bytes, size_t length) {
    const auto* data = static_cast<const u8*>(bytes);
    while (length) {
        const u32 amount = length > 1024 ? 1024 : static_cast<u32>(length);
        const i64 count = state.files.write(state.handle, data, amount);
        response(state, count, "generation staging write outcome is not confirmed");
        require(count > 0 && static_cast<u64>(count) <= amount, "short generation staging write");
        data += count;
        length -= static_cast<size_t>(count);
    }
}
void create(staging_context& state, const char* path, bool (*canonical_path)(const char*)) {
    parent_directories(state, path, canonical_path);
    u32 size = 0, version = 0;
    require(!state.handle, "staging already owns a handle");
    response(state, state.files.open(path, xos::file::write_only | xos::file::open_create |
                                    xos::file::open_exclusive, state.handle, size, version),
             "cannot exclusively create generation staging object");
    require(state.handle && !size, "new staging object is not empty");
}
}

void stage(staging_context& state, const char* repository, const plan& prepared,
           uint64_t absolute_deadline, bool (*canonical_path)(const char*)) {
    using namespace xypm_native;
    require(!state.quarantined && !state.handle && !state.pin_count && absolute_deadline &&
            state.files.set_deadline(absolute_deadline), "staging context is quarantined or deadline invalid");
    require(state.files.init(), "cannot initialize generation staging file session");
    for (u32 i = 0; i < prepared.generation.header.object_count; ++i) {
        const auto& object = prepared.generation.objects[i];
        if (already_staged(state, object.path, object.file_bytes, object.sha256, canonical_path)) continue;
        char package_path[256];
        const auto& source = prepared.sources[i];
        xypm_repository::package_path(repository, source.package_sha256, package_path);
        const u64 size = xypm_repository::open_regular(package_path, canonical_path);
        const auto package = verify_package(xypm_repository::opened_file, size);
        require(!std::strcmp(package.digest, source.package_sha256), "package changed before staging");
        require(source.payload_offset <= size && object.file_bytes <= size - source.payload_offset &&
                source.payload_offset <= LONG_MAX && std::fseek(xypm_repository::opened_file,
                    static_cast<long>(source.payload_offset), SEEK_SET) == 0, "cannot seek verified object payload");
        create(state, object.path, canonical_path);
        u64 remaining = object.file_bytes;
        unsigned char block[2048];
        while (remaining) {
            const size_t amount = remaining > sizeof(block) ? sizeof(block) : static_cast<size_t>(remaining);
            require(std::fread(block, 1, amount, xypm_repository::opened_file) == amount,
                    "verified package changed while staging");
            write(state, block, amount);
            remaining -= amount;
        }
        const int closed = std::fclose(xypm_repository::opened_file);
        xypm_repository::opened_file = nullptr;
        require(closed == 0, "cannot close staged package source");
        close(state);
        response(state, state.files.sync(), "generation object sync outcome is not confirmed");
        checkpoint(state);
        require(already_staged(state, object.path, object.file_bytes, object.sha256, canonical_path),
                "staged generation object disappeared");
    }
    unsigned char digest[32];
    sha256 hash;
    hash.update(&prepared.generation, prepared.generation.header.size);
    hash.finish(digest);
    char text[65];
    hex_digest(digest, text);
    require(!std::strcmp(text, prepared.authenticated.generation_sha256), "prepared manifest changed");
    if (!already_staged(state, prepared.manifest_path, prepared.generation.header.size, digest, canonical_path)) {
        create(state, prepared.manifest_path, canonical_path);
        write(state, &prepared.generation, prepared.generation.header.size);
        close(state);
        response(state, state.files.sync(), "generation manifest sync outcome is not confirmed");
        checkpoint(state);
        require(already_staged(state, prepared.manifest_path, prepared.generation.header.size, digest, canonical_path),
                "staged generation manifest disappeared");
    }
}

void release_staging(staging_context& state) {
    xypm_native::require(!state.quarantined && !state.handle, "cannot release quarantined staging");
    for (u32 i = 0; i < state.pin_count; ++i) {
        if (!state.pins[i]) continue;
        // Retain ownership if close is not confirmed; never replay the close.
        response(state, state.files.close(state.pins[i]), "generation pin close outcome is not confirmed");
        state.pins[i] = 0;
    }
    state.pin_count = 0;
}
}
