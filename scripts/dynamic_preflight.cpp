// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_elf.hpp>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>

namespace {
xos::dynamic::generation approved;
xos::dynamic::elf_image images[xos::dynamic::generation_max_objects];
bool read(void* context, xos::u64 offset, xos::u8* destination, xos::u32 length) {
    const auto& bytes = *static_cast<const std::vector<xos::u8>*>(context);
    if (offset > bytes.size() || length > bytes.size() - offset) return false;
    for (xos::u32 i = 0; i < length; ++i) destination[i] = bytes[offset + i];
    return true;
}
std::vector<xos::u8> file(const char* path) {
    std::ifstream input(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(input), std::istreambuf_iterator<char>()};
}
}
int main(int argc, char** argv) {
    using namespace xos;
    using namespace xos::dynamic;
    if (argc < 6) return 64;
    const auto manifest = file(argv[1]);
    if (manifest.size() < sizeof(generation_header) || manifest.size() > sizeof(approved)) return 65;
    for (usize i = 0; i < manifest.size(); ++i) reinterpret_cast<u8*>(&approved)[i] = manifest[i];
    if (approved.header.size != manifest.size() || argc != static_cast<int>(approved.header.object_count) + 2
        || validate_generation(approved) != error::none) return 66;
    for (u32 index = 0; index < approved.header.object_count; ++index) {
        auto bytes = file(argv[index + 2]);
        auto result = verify_object(read, &bytes, approved.objects[index]);
        if (result == error::none && index) result = inspect_elf(read, &bytes, approved, index, images[index]);
        if (result == error::none && !index) {
            elf::load_plan plan{};
            if (elf::inspect_reader(read, &bytes, bytes.size(), 62, plan) != elf::error::none) result = error::header;
        }
        std::printf("DYNAMIC_PREFLIGHT object=%u error=%u symbols=%u relocations=%u versions=%u\n",
            index, static_cast<u32>(result), images[index].symbol_count,
            images[index].relocation_count, images[index].version_count);
        if (result != error::none) return 67;
    }
    const auto versions = check_versions(approved, images);
    std::printf("DYNAMIC_PREFLIGHT closure=%u\n", static_cast<u32>(versions));
    return versions == error::none ? 0 : 68;
}
