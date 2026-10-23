#include <xos/elf.hpp>
#include <fstream>
#include <vector>

int main(int argc, char** argv) {
    if (argc != 2 || xos::elf::self_check(62) != 24) { return 1; }
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<xos::u8> original((std::istreambuf_iterator<char>(file)), {});
    if (original.empty()) { return 2; }
    xos::elf::load_plan plan{};
    if (xos::elf::inspect(original.data(), original.size(), 62, plan) != xos::elf::error::none) { return 3; }
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
