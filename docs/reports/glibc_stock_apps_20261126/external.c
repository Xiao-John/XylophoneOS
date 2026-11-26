/* SPDX-License-Identifier: Apache-2.0 */
#include <gnu/libc-version.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    FILE *state = fopen("/state/user.txt", "r");
    if (!state)
        return 2;
    char seed[64];
    int valid = fgets(seed, sizeof(seed), state) && strcmp(seed, "glibc-user-data\n") == 0;
    if (fclose(state) || !valid)
        return 3;
    const char *version = gnu_get_libc_version();
    if (strcmp(version, "2.44"))
        return 4;
    printf("GLIBC_KIT_C_OK %s\n", version);
    return 0;
}
