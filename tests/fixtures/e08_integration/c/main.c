/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include "project.h"
int main(void) {
    int value = project_adjust(20, 22);
    printf("%s_V1_%d\n", project_label(), value);
    return value == 42 ? 0 : 1;
}
