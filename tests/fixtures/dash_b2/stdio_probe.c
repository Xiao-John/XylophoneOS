/* SPDX-License-Identifier: Apache-2.0 */
#include <unistd.h>

int main(void) {
    if (write(1, "OUT\n", 4) != 4) { return 1; }
    if (write(2, "ERR\n", 4) != 4) { return 2; }
    return 0;
}
