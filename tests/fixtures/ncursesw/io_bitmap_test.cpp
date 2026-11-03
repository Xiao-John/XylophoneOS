// SPDX-License-Identifier: Apache-2.0
#include "io_bitmap.hpp"
using namespace xos::arch;

int main() {
    io_bitmap map{};
    map.deny_all();
    for (xos::u32 port = 0; port < io_bitmap::port_count; ++port)
        if (map.allowed(port)) return 1;
    if (map.set_range(65536, 1, true) || map.set_range(65535, 2, true) ||
        map.set_range(0, 0, true) || map.allowed(65536)) return 2;
    if (!map.set_range(0x3f8, 8, true) || map.allowed(0x3f7) || map.allowed(0x400)) return 3;
    for (xos::u32 port = 0x3f8; port < 0x400; ++port) if (!map.allowed(port)) return 4;
    if (!map.set_range(0x3fb, 2, false) || map.allowed(0x3fb) || map.allowed(0x3fc) ||
        !map.allowed(0x3fa) || !map.allowed(0x3fd)) return 5;
    if (!map.set_range(65535, 1, true) || !map.allowed(65535) || map.data[io_bitmap::bytes] != 0xff) return 6;
    map.deny_all();
    if (map.allowed(0x3f8) || map.allowed(65535) || map.data[io_bitmap::bytes] != 0xff) return 7;
    return 0;
}
