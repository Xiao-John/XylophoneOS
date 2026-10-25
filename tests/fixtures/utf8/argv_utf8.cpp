// SPDX-License-Identifier: Apache-2.0
#include <stdio.h>

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i) { printf("arg%d=%s\n", i, argv[i]); }
    return 0;
}
