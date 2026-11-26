// SPDX-License-Identifier: Apache-2.0
#include <xos/fault_sha256.hpp>
#include <xos/vm.hpp>
#include "glibc_d1/image_mapping.hpp"
#include "image_reader.hpp"

using namespace xos;
using namespace xos::glibc_d1;

// Only the verified load descriptors and expected digest are embedded.
#include "native_image_plan.hpp"

namespace {
constexpr u64 biases[] = {0x100000200000ull, 0x180040000000ull};

int fail(const char* stage, const image_map_result& result = {}) {
    sdk::print("D1_NATIVE_MAP_FAIL "); sdk::print(stage);
    sdk::print(" error="); sdk::decimal(static_cast<u32>(result.error));
    sdk::print(" vm="); sdk::signed_decimal(result.vm_error);
    sdk::print(" rollback="); sdk::signed_decimal(result.rollback_error);
    sdk::print("\n");
    return 1;
}

bool same_object(loader::opened_file& source) {
    if (source.size != file_bytes) { return false; }
    sha256 hash;
    u8 buffer[1024];
    constexpr auto buffer_bytes = static_cast<u32>(sizeof(buffer));
    for (u32 offset = 0; offset < source.size;) {
        const u32 length = source.size - offset < buffer_bytes ? source.size - offset : buffer_bytes;
        if (!loader::file_read(&source, offset, buffer, length)) { return false; }
        hash.update(buffer, length);
        offset += length;
    }
    u8 digest[32];
    hash.finish(digest);
    for (u32 index = 0; index < sizeof(digest); ++index) {
        if (digest[index] != wanted_digest[index]) { return false; }
    }
    return true;
}

mapped_image layout(u64 bias) {
    return {bias, entry_offset, loads, sizeof(loads) / sizeof(loads[0])};
}

struct short_reader { loader::opened_file* source; u32 reads; };
bool short_read(void* context, u64 offset, u8* bytes, u32 length) {
    auto& state = *static_cast<short_reader*>(context);
    if (++state.reads != 2) { return loader::file_read(state.source, offset, bytes, length); }
    // A short transfer before reporting failure still requires full rollback.
    (void)loader::file_read(state.source, offset, bytes, length / 2);
    return false;
}

bool restate(u64 address) {
    if (sdk::vm_reserve(address, image_span, vm_page_size, true) != static_cast<i64>(address)) {
        return false;
    }
    return sdk::vm_change(vm_operation::unmap, address, image_span) == 0;
}

bool execute(u64 bias) {
    for (const auto& load : loads) {
        const auto* bytes = reinterpret_cast<const u8*>(bias + load.address);
        for (u64 offset = load.file_bytes; offset < load.memory_bytes; ++offset) {
            if (bytes[offset] != 0) { return false; }
        }
    }
    // The linked fixture has exactly one verified relative data relocation.
    auto* cell = reinterpret_cast<u64*>(bias + relocation_site);
    *cell = bias + relocated_data;
    if (sdk::vm_change(vm_operation::protect, bias + relro_start, relro_size,
                       vm_protection::read) != 0) { return false; }
    auto* data = reinterpret_cast<const u64*>(*cell);
    if (*data != 0x4090) { return false; }
    const auto entry = reinterpret_cast<u64 (*)(u64)>(bias + entry_offset);
    const u64 first = entry(1023);
    const u64 second = entry(1023);
    if (first != 0x448f || second != 0x4c8d || *data != second) { return false; }
    sdk::print("D1_NATIVE_MAP "); sdk::decimal(bias); sdk::print(" ");
    sdk::decimal(first); sdk::print(" "); sdk::decimal(second); sdk::print("\n");
    return true;
}
}

extern "C" int xos_user_main(const startup_info*) {
    file::client files;
    u32 handle = 0, size = 0, version = 0;
    if (!files.init() || files.open("/bin/layout.so", file::read_only | file::open_pin,
                                    handle, size, version) != 0) { return fail("pin"); }
    loader::opened_file source{&files, handle, size, loader::file_read_mode::positioned};
    if (files.seek(handle, 73) != 73 || !same_object(source)) { return fail("identity"); }
    constexpr image_map_budget budget{image_span, image_span};
    image_allocation unused{};
    const auto too_small = map_verified_image(layout(biases[0]), size, loader::file_read, &source,
                                              {image_span - vm_page_size, image_span}, unused);
    if (too_small.error != image_map_error::budget || unused.bytes != 0 || !restate(biases[0])) {
        return fail("budget", too_small);
    }
    short_reader short_input{&source, 0};
    const auto short_result = map_verified_image(layout(biases[0]), size, short_read,
                                                  &short_input, budget, unused);
    if (short_result.error != image_map_error::read || short_result.rollback_error != 0 ||
        short_input.reads != 2 || unused.bytes != 0 || !restate(biases[0])) {
        return fail("short-read cleanup", short_result);
    }
    image_allocation images[2]{};
    for (u32 index = 0; index < 2; ++index) {
        const auto result = map_verified_image(layout(biases[index]), size, loader::file_read,
                                               &source, budget, images[index]);
        if (result.error != image_map_error::none) { return fail("map", result); }
    }
    const auto collision = map_verified_image(layout(biases[0]), size, loader::file_read, &source,
                                              budget, unused);
    if (collision.error != image_map_error::reserve || collision.vm_error != vm_error_collision ||
        collision.rollback_error != 0 || unused.bytes != 0) { return fail("collision", collision); }
    if (files.seek(handle, 0, file::seek_current) != 73 || files.close(handle) != 0) {
        return fail("reader cursor and close");
    }
    for (u32 index = 0; index < 2; ++index) {
        if (!execute(biases[index]) || release_image(images[index]) != 0 ||
            images[index].bytes != 0 || !restate(biases[index])) { return fail("execute and release"); }
    }
    sdk::print("D1_NATIVE_MAP_OK pin=verified offset=preserved bss=zero rollback=complete\n");
    return 0;
}
