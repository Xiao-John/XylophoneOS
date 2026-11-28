// SPDX-License-Identifier: Apache-2.0
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    char line[64];
    if (argc != 2) return 10;
    int length = snprintf(line, sizeof(line), "%s\n", argv[1]);
    if (length <= 0 || (size_t)length >= sizeof(line)) return 11;
    int file = open("/state/user.txt", O_WRONLY | O_APPEND);
    if (file < 0) return 12;
    if (write(file, line, (size_t)length) != length) { close(file); return 13; }
    if (close(file)) return 14;
    printf("P0_R1_FROZEN_OK %s\n", argv[1]);
    return 0;
}
