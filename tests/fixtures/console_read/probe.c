/* SPDX-License-Identifier: Apache-2.0 */
/* Blocking console read: waits for a line and reports the bytes. */
#include <stdio.h>
#include <unistd.h>

int main(void) {
    char buffer[32];
    ssize_t got = 0;
    while (got < (ssize_t)sizeof(buffer)) {
        const ssize_t chunk = read(0, buffer + got, 1);
        if (chunk <= 0) { break; }
        ++got;
        if (buffer[got - 1] == '\n') { break; }
    }
    printf("read=%ld", (long)got);
    for (ssize_t i = 0; i < got; ++i) {
        printf(" %02x", (unsigned char)buffer[i]);
    }
    printf("\n");
    return got > 0 ? 0 : 1;
}
