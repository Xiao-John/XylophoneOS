// SPDX-License-Identifier: Apache-2.0
#include <unistd.h>

static unsigned state;

static void __attribute__((constructor(200))) first_init(void)
{
    state = 1;
}

static void __attribute__((constructor(300))) second_init(void)
{
    state = state * 10 + 2;
}

static void __attribute__((destructor(300))) second_fini(void)
{
    state = state * 10 + 3;
}

static void __attribute__((destructor(200))) first_fini(void)
{
    if (state == 123)
    {
        static const char report[] = "GLIBC_CTOR_ORDER_PASS\n";
        (void) write(STDOUT_FILENO, report, sizeof(report) - 1);
    }
}

int main(void)
{
    return state == 12 ? 0 : 1;
}
