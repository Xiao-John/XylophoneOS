/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define CHECK(expression) do {                                                  \
    if (!(expression)) {                                                        \
        fprintf(stderr, "PROCESS_SPAWN_FAILURE line=%d errno=%d\n", __LINE__, errno); \
        return 1;                                                               \
    }                                                                           \
} while (0)

static int child(const char *mode)
{
    char path[256];
    CHECK(getcwd(path, sizeof(path)) == path && strcmp(path, "/g3_spawn") == 0);
    const char *marker = getenv("XOS_SPAWN_MARKER");
    CHECK(marker != NULL && strcmp(marker, "present") == 0);
    CHECK(fcntl(3, F_GETFD) == -1 && errno == EBADF);
    if (strcmp(mode, "hold") == 0) {
        struct timespec start, now;
        CHECK(clock_gettime(CLOCK_MONOTONIC, &start) == 0);
        while (access("gate", F_OK) != 0) {
            CHECK(errno == ENOENT);
            CHECK(clock_gettime(CLOCK_MONOTONIC, &now) == 0 && now.tv_sec - start.tv_sec < 8);
            CHECK(sched_yield() == 0);
        }
        puts("GLIBC_SPAWN_CHILD_23");
        return 23;
    }
    CHECK(strcmp(mode, "zero") == 0);
    puts("GLIBC_SPAWN_CHILD_0");
    return 0;
}

int main(int argc, char **argv)
{
    if (argc == 3 && strcmp(argv[1], "child") == 0) {
        return child(argv[2]);
    }
    CHECK(argc == 2);
    CHECK(chdir("/g3_spawn") == 0);
    char *arguments[] = { "child", "child", "zero", NULL };
    char *environment[] = { "XOS_SPAWN_MARKER=present", NULL };
    pid_t pid = -99;
    int status = 0x12345678;
    if (strcmp(argv[1], "denied") == 0) {
        errno = EDOM;
        int refused = posix_spawn(&pid, "child", NULL, NULL, arguments, environment);
        CHECK(refused == EPERM && pid == -99 && errno == EDOM);
        CHECK(waitpid(-1, &status, WNOHANG) == -1 && errno == ECHILD && status == 0x12345678);
        puts("GLIBC_SPAWN_DENIED_PASS");
        return 0;
    }
    CHECK(strcmp(argv[1], "parent") == 0);
    CHECK(waitpid(-1, &status, WNOHANG) == -1 && errno == ECHILD && status == 0x12345678);
    CHECK(waitpid(0, &status, 0) == -1 && errno == ENOTSUP);
    CHECK(waitpid(-1, &status, WUNTRACED) == -1 && errno == ENOTSUP);
    CHECK(posix_spawn(&pid, "missing", NULL, NULL, arguments, environment) == ENOENT && pid == -99);
    CHECK(posix_spawn(&pid, "plain.txt", NULL, NULL, arguments, environment) == ENOEXEC && pid == -99);

    posix_spawnattr_t attr;
    posix_spawn_file_actions_t actions;
    CHECK(posix_spawnattr_init(&attr) == 0 && posix_spawn_file_actions_init(&actions) == 0);
    CHECK(posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP) == 0);
    CHECK(posix_spawn(&pid, "child", &actions, &attr, arguments, environment) == ENOTSUP && pid == -99);
    CHECK(posix_spawnattr_setflags(&attr, 0) == 0);
    CHECK(posix_spawn_file_actions_addclose(&actions, 0) == 0);
    CHECK(posix_spawn(&pid, "child", &actions, &attr, arguments, environment) == ENOTSUP && pid == -99);
    CHECK(posix_spawn_file_actions_destroy(&actions) == 0 && posix_spawn_file_actions_init(&actions) == 0);

    int input_flags = fcntl(STDIN_FILENO, F_GETFL);
    CHECK(input_flags >= 0 && fcntl(STDIN_FILENO, F_SETFL, input_flags | O_NONBLOCK) == 0);
    CHECK(posix_spawn(&pid, "child", NULL, NULL, arguments, environment) == ENOTSUP && pid == -99);
    CHECK(fcntl(STDIN_FILENO, F_SETFL, input_flags) == 0);

    int fd = open("plain.txt", O_RDONLY);
    CHECK(fd == 3);
    CHECK(posix_spawn(&pid, "child", &actions, &attr, arguments, environment) == ENOTSUP && pid == -99);
    CHECK(fcntl(fd, F_SETFD, FD_CLOEXEC) == 0);
    errno = EDOM;
    CHECK(posix_spawn(&pid, "child", &actions, &attr, arguments, environment) == 0 && pid > 0 && errno == EDOM);
    CHECK(posix_spawnattr_destroy(&attr) == 0 && posix_spawn_file_actions_destroy(&actions) == 0);
    CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    status = 0x12345678;
    CHECK(waitpid(pid, &status, 0) == -1 && errno == ECHILD && status == 0x12345678);
    CHECK(close(fd) == 0);

    CHECK(unlink("gate") == 0 || errno == ENOENT);
    arguments[2] = "hold";
    CHECK(posix_spawn(&pid, "./child", NULL, NULL, arguments, environment) == 0 && pid > 0);
    CHECK(waitpid(0, &status, WNOHANG) == -1 && errno == ENOTSUP && status == 0x12345678);
    CHECK(waitpid(-2, &status, WNOHANG) == -1 && errno == ENOTSUP && status == 0x12345678);
    CHECK(waitpid(pid, &status, WNOHANG) == 0 && status == 0x12345678);
    CHECK(waitpid(-1, &status, WNOHANG) == 0 && status == 0x12345678);
    fd = open("gate", O_CREAT | O_WRONLY, 0600);
    CHECK(fd >= 0 && close(fd) == 0);
    CHECK(waitpid(-1, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == 23);
    CHECK(unlink("gate") == 0);
    status = 0x12345678;
    CHECK(wait(&status) == -1 && errno == ECHILD && status == 0x12345678);
    puts("GLIBC_SPAWN_WAIT_PASS");
    return 0;
}
