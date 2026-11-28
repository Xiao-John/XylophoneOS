/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef APPLICATION_REVISION
#define APPLICATION_REVISION 1
#endif

int main(void) {
    char *message = malloc(128);
    if (!message) return 10;
    int length = snprintf(message, 128, "P1D_EXTERNAL_APPLICATION revision=%d libc=GNU\n", APPLICATION_REVISION);
    if (length <= 0 || length >= 128 || strlen(message) != (size_t)length) {
        free(message);
        return 11;
    }
    int result = fputs(message, stdout);
    free(message);
    return result < 0 ? 12 : 0;
}
