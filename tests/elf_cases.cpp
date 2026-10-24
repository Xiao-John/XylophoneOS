// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/elf.hpp>
#include <fstream>
#include <vector>

struct reader_context { const std::vector<xos::u8>* bytes; unsigned calls; unsigned fail_at; };
bool read_exact(void* raw, xos::u64 offset, xos::u8* destination, xos::u32 length) {
    auto& context = *static_cast<reader_context*>(raw);
    if (++context.calls == context.fail_at || offset > context.bytes->size() ||
        length > context.bytes->size() - offset) return false;
    for(xos::u32 i=0;i<length;++i) destination[i]=(*context.bytes)[offset+i];
    return true;
}
int main(int argc, char** argv) {
    if (argc != 2 || xos::elf::self_check(62) != 24) { return 1; }
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<xos::u8> original((std::istreambuf_iterator<char>(file)), {});
    if (original.empty()) { return 2; }
    xos::elf::load_plan plan{};
    if (xos::elf::inspect(original.data(), original.size(), 62, plan) != xos::elf::error::none) { return 3; }
    reader_context context{&original,0,0};
    if (xos::elf::inspect_reader(read_exact,&context,original.size(),62,plan) != xos::elf::error::none || context.calls != 2) return 4;
    for(unsigned fail=1;fail<=2;++fail) {
        context.calls=0;context.fail_at=fail;
        if(xos::elf::inspect_reader(read_exact,&context,original.size(),62,plan)!=xos::elf::error::io) return 5;
    }
    // Truncated buffers and deterministic hostile header mutations under ASan/UBSan.
    for (xos::u64 length = 0; length < original.size(); length += 31) {
        (void)xos::elf::inspect(original.data(), length, 62, plan);
    }
    xos::u32 seed = 0x584f53;
    for (xos::u32 i = 0; i < 512; ++i) {
        auto bytes = original;
        seed = seed * 1664525u + 1013904223u;
        const auto offset = (seed >> 8) % 256;
        for (xos::u32 j = 0; j < 8; ++j) { bytes[offset + j] ^= static_cast<xos::u8>(seed >> (j % 4 * 8)); }
        (void)xos::elf::inspect(bytes.data(), bytes.size(), 62, plan);
    }
    return 0;
}
