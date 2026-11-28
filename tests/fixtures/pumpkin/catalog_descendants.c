/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <spawn.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static int launch_leaf(const char *path) {
    pid_t child = 0;
    char *arguments[] = {(char *)path, "leaf", 0};
    int result = posix_spawn(&child, path, 0, 0, arguments, environ);
    if (result) return result;
    int status = 0;
    return waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0 ? 0 : EIO;
}

int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "leaf") == 0) return 0;
    if (argc != 3) return 2;
    if (strcmp(argv[1], "reexec") == 0) {
        char *arguments[] = {argv[0], "tree", argv[2], 0};
        execv(argv[0], arguments);
        return 3;
    }
    if (strcmp(argv[1], "tree") != 0) return 4;
    /* Serialize successful leaf launches before creating the next descendant:
       the native eight-process budget remains unchanged. */
    if (launch_leaf(argv[0]) != 0) return 7;
    pid_t owned = fork();
    if (owned < 0) return 5;
    if (owned == 0) {
        if (launch_leaf(argv[0]) != 0) return 7;
        owned = fork();
        if (owned < 0) return 6;
        if (owned == 0 && launch_leaf(argv[0]) != 0) return 7;
    }
    if (write(1, "R", 1) != 1) return 8;
    char go = 0;
    if (read(0, &go, 1) != 1 || go != 'G') return 9;
    /* All three processes were live at the barrier. Reap bottom-up before
       requesting another private constructor/launch-control transaction. */
    if (owned > 0) {
        int status = 0;
        if (waitpid(owned, &status, 0) != owned || !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 11;
    }
    int result = launch_leaf(argv[0]);
    int denied = strcmp(argv[2], "deny") == 0 ? result == EPERM : result != 0;
    if (!denied || write(1, "D", 1) != 1) return 10;
    return 0;
}
