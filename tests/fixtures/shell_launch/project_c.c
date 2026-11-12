/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include "project.h"
int main(void) {
    if (project_value() != 42) return 1;
    puts("SL3_C_OK");
    return 0;
}
