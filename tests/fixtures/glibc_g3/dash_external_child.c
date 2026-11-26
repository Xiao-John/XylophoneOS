/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    char cwd[32];
    const char *token = getenv("DASH_GLIBC_TOKEN");
    if (argc != 4 || strcmp(argv[2], "two words") != 0 || argv[3][0] != '\0' ||
        token == NULL || strcmp(token, "ordinary value") != 0 ||
        getcwd(cwd, sizeof(cwd)) == NULL || strcmp(cwd, "/cases") != 0) {
        puts("DASH_GLIBC_CHILD_BAD_INPUT");
        return 95;
    }
    if (strcmp(argv[1], "explicit") == 0 && strcmp(argv[0], "/bin/preview_child") == 0) {
        puts("DASH_GLIBC_CHILD_EXPLICIT argv_env_cwd=ok");
        return 0;
    }
    if (strcmp(argv[1], "path") == 0 && strcmp(argv[0], "preview_child") == 0) {
        puts("DASH_GLIBC_CHILD_PATH argv_env_cwd=ok");
        return 23;
    }
    puts("DASH_GLIBC_CHILD_BAD_COMMAND");
    return 96;
}
