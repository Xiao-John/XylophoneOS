// SPDX-License-Identifier: Apache-2.0
#include "addresses.h"
#include <stdio.h>

int main(void)
{
    if (!check_addresses())
        return 1;
    puts("GLIBC_INET_C_PASS layout bytes symbols ipv6");
    return 0;
}
