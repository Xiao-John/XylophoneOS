/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include <unistd.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

int main(void) {
    const char ready[] = "W1_FAULT_APP_READY\n";
    for (unsigned i = 0; i < sizeof(ready) - 1; ++i)
        if (write(1, ready + i, 1) != 1) return 1;
    char byte;
    return read(0, &byte, 1) < 0 ? 0 : 2;
}
