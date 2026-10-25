// SPDX-License-Identifier: Apache-2.0
// U0/U1 acceptance sample: UTF-8 source literals must survive compilation,
// process output and the serial text path byte-for-byte.
#include <stdio.h>

int main() {
    fputs("Wir müssen wissen, Wir werden wissen.\n", stdout);
    fputs("我们必须知道，我们终将知道。\n", stdout);
    return 0;
}
