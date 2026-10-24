// SPDX-License-Identifier: Apache-2.0
#include <xos/elf.hpp>
#include <cstdio>
#include <cstring>

namespace {
unsigned char bytes[12288];
void put(unsigned offset, xos::u64 value, unsigned length) {
    for (unsigned i = 0; i < length; ++i) bytes[offset + i] = static_cast<unsigned char>(value >> (8 * i));
}
void reset() {
    std::memset(bytes, 0, sizeof(bytes));
    put(0, 0x464c457f, 4); bytes[4] = 2; bytes[5] = 1; bytes[6] = 1;
    put(16, 2, 2); put(18, 62, 2); put(20, 1, 4);
    put(24, xos::process_user_begin, 8); put(32, 64, 8);
    put(52, 64, 2); put(54, 56, 2); put(56, 3, 2);
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned p = 64 + 56 * i;
        put(p, 1, 4); put(p + 4, i ? 6 : 5, 4);
        put(p + 8, 4096 + 4096 * i, 8);
        put(p + 16, xos::process_user_begin + 0x3000 * i, 8);
        put(p + 32, 16, 8); put(p + 40, 4096, 8); put(p + 48, 4096, 8);
    }
    const unsigned p = 176;
    put(p, 7, 4); put(p + 4, 4, 4); put(p + 8, 8192, 8);
    put(p + 16, xos::process_user_begin + 0x3000, 8);
    put(p + 32, 16, 8); put(p + 40, 8192, 8); put(p + 48, 16, 8);
}
}
int main() {
    using xos::elf::error;
    for (unsigned test = 0; test < 12; ++test) {
        reset();
        error expected = error::none;
        switch (test) {
        case 0: break;
        case 1: put(176 + 32, 8193, 8); expected = error::bounds; break;
        case 2: put(176 + 8, ~xos::u64{0}, 8); expected = error::bounds; break;
        case 3: put(176 + 48, 3, 8); expected = error::alignment; break;
        case 4: put(176 + 40, xos::process_tls_max_bytes + 1, 8); expected = error::too_large; break;
        case 5: put(176 + 8, 8208, 8); expected = error::bounds; break;
        case 6: put(176 + 4, 5, 4); expected = error::unsupported; break;
        case 7: put(120 + 16, xos::process_tls_begin, 8); expected = error::bounds; break;
        case 8:
            put(56, 4, 2); std::memcpy(bytes + 232, bytes + 176, 56);
            expected = error::unsupported; break;
        case 9: put(176 + 32, 0, 8); break; // Pure .tbss needs no file template.
        case 10: put(176 + 48, xos::process_tls_max_alignment * 2, 8); expected = error::alignment; break;
        case 11: put(176 + 16, xos::process_user_begin + 0x3001, 8); expected = error::alignment; break;
        }
        xos::elf::load_plan plan{};
        const auto actual = xos::elf::inspect(bytes, sizeof(bytes), 62, plan);
        if (actual != expected || (actual == error::none && !plan.tls.present)) {
            std::fprintf(stderr, "TLS case %u: %s != %s\n", test,
                         xos::elf::error_name(actual), xos::elf::error_name(expected));
            return 1;
        }
    }
    std::puts("PASS: 12 static TLS metadata cases");
}
