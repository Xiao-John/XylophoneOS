// SPDX-License-Identifier: Apache-2.0
#include <fcntl.h>
#include <gnu/libc-version.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int initialized;
static _Thread_local int tls_value = 31;
__attribute__((constructor)) static void initialize(void) { initialized = 19; }

int main(int argc, char **argv)
{
    char line[64];
    if (argc != 2 || initialized != 19 || tls_value != 31 || strcmp(gnu_get_libc_version(), "2.44"))
        return 20;
    int length = snprintf(line, sizeof(line), "c-%s\n", argv[1]);
    if (length <= 0 || (size_t)length >= sizeof(line)) return 21;
    int file = open("/state/user.txt", O_WRONLY | O_APPEND);
    if (file < 0) return 22;
    if (write(file, line, (size_t)length) != length) { close(file); return 23; }
    if (close(file)) return 24;
    printf("P0_R1_GLIBC_C_OK %s libc=%s constructor=1 tls=1\n", argv[1], gnu_get_libc_version());
    return 0;
}
