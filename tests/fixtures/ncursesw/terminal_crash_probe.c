/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include <unistd.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

int main(void) {
    const char text[] = "W1_CRASH_READY\n";
    for (unsigned i = 0; i < sizeof(text) - 1; ++i)
        if (write(1, text + i, 1) != 1) return 1;
    *(volatile unsigned char *)(uintptr_t)0x100000 = 1;
    return 2;
}
