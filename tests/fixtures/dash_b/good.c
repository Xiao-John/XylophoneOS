/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include "value.h"
int main(void) {
    printf("c_app=%d\n", answer_value());
    return answer_value() == 42 ? 0 : 1;
}
