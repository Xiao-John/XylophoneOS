#include <xos/elf.hpp>

namespace xos::elf {
namespace {
u8 fixture[12288];
void put(u64 offset, u64 value, u32 count) {
    for (u32 i = 0; i < count; ++i) { fixture[offset + i] = static_cast<u8>(value >> (i * 8)); }
}
void reset(u16 machine) {
    for (auto& byte : fixture) { byte = 0; }
    put(0, 0x464c457f, 4); fixture[4] = 2; fixture[5] = 1; fixture[6] = 1;
    put(16, 2, 2); put(18, machine, 2); put(20, 1, 4);
    put(24, process_user_begin, 8); put(32, 64, 8);
    put(52, 64, 2); put(54, 56, 2); put(56, 2, 2);
    for (u32 i = 0; i < 2; ++i) {
        const u64 at = 64 + u64{i} * 56;
        put(at, 1, 4); put(at + 4, i == 0 ? 5 : 6, 4);
        put(at + 8, 4096 + u64{i} * 4096, 8);
        put(at + 16, process_user_begin + u64{i} * 0x3000, 8);
        put(at + 32, 16, 8); put(at + 40, 4096, 8); put(at + 48, 4096, 8);
    }
}
}
u32 self_check(u16 machine) {
    for (u32 test = 0; test < 24; ++test) {
        reset(machine);
        error expected = error::none;
        u64 size = sizeof(fixture);
        switch (test) {
        case 0: break;
        case 1: fixture[0] = 0; expected = error::header; break;
        case 2: put(18, machine + 1, 2); expected = error::target; break;
        case 3: put(16, 3, 2); expected = error::target; break;
        case 4: put(64, 3, 4); expected = error::unsupported; break;
        case 5: put(64 + 32, 4097, 8); expected = error::bounds; break;
        case 6: put(64 + 8, ~u64{0}, 8); expected = error::bounds; break;
        case 7: put(64 + 16, ~u64{0}, 8); expected = error::bounds; break;
        case 8: put(120 + 16, process_user_begin, 8); expected = error::overlap; break;
        case 9: put(24, process_user_begin + 0x3000, 8); expected = error::entry; break;
        case 10: put(64 + 4, 7, 4); expected = error::permissions; break;
        case 11: put(64 + 48, 3, 8); expected = error::alignment; break;
        case 12: put(32, ~u64{0}, 8); expected = error::bounds; break;
        case 13: put(64 + 40, ~u64{0}, 8); expected = error::bounds; break;
        case 14: put(64, 2, 4); expected = error::unsupported; break;
        case 15: put(64, 7, 4); expected = error::unsupported; break;
        case 16: put(54, 55, 2); expected = error::bounds; break;
        case 17: put(64 + 8, 4097, 8); expected = error::alignment; break;
        case 18: put(24, process_user_begin + 128, 8); expected = error::entry; break;
        case 19:
            put(120 + 16, process_user_begin + 16, 8); put(120 + 8, 8192 + 16, 8);
            put(64 + 40, 16, 8); put(120 + 40, 16, 8); expected = error::overlap; break;
        case 20: put(64 + 16, process_image_end, 8); expected = error::bounds; break;
        case 21: put(64 + 40, 64 * 4096, 8); expected = error::too_large; break;
        case 22: size = 63; expected = error::header; break;
        case 23: put(64, 0, 4); put(120, 0, 4); expected = error::entry; break;
        default: break;
        }
        load_plan plan{};
        if (inspect(fixture, size, machine, plan) != expected) { return test; }
    }
    return 24;
}
}
