/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <sys/stat.h>

int main(void)
{
    if (chmod("/g3_cwd/read-only.txt", 0444) != 0) {
        perror("chmod");
        return 1;
    }
    puts("GLIBC_CWD_READONLY_READY");
    return 0;
}
