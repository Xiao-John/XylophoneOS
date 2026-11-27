/* SPDX-License-Identifier: Apache-2.0 */
#include <gnu/libc-version.h>
#include <stdio.h>
#include "project.h"

int main(void) {
    if (project_value() != 42)
        return 1;
    printf("GLIBC_GNU_SEED_C=%s\n", gnu_get_libc_version());
    return 0;
}
