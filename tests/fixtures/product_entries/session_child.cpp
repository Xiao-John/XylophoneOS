// SPDX-License-Identifier: Apache-2.0
#include <cstdio>

int main(int argc, char** argv) {
    if (argc == 1) {
        std::printf("BROWSER_ENTRY %s\n", argv[0]);
        return 0;
    }
    if (argc != 3) return 1;
    std::printf("DESKTOP_ENTRY %s\n", argv[0]);
    if (argv[2][0] == '\0') return 18;
    std::printf("DESKTOP_RESUMED %s\n", argv[2]);
    return 0;
}
