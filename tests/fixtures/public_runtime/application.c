/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

extern char **environ;
static __thread unsigned tls_value = 31;
static int initialized;
static int sample(void) { return 47; }
static int (*relative_function)(void) = sample;
__attribute__((constructor)) static void initialize(void)
{
    initialized = 19;
    if (getenv("P0_READY_CONSTRUCTOR")) {
        /* A parent must not return from posix_spawn while this executable's
           initializer is still running. The delay makes an early rtld READY
           observable before the completed constructor publishes its file. */
        const struct timespec delay = {0, 100000000};
        if (nanosleep(&delay, NULL) != 0) _Exit(51);
        const int fd = open("/tests/constructor_ready", O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0 || write(fd, "READY", 5) != 5 || close(fd) != 0) _Exit(52);
    }
}

static int descriptor(const char *name)
{
    const char *value = getenv(name);
    return value ? atoi(value) : -1;
}
static int number_environment(const char *name, long value)
{
    char text[32];
    if (snprintf(text, sizeof(text), "%ld", value) <= 0) return -1;
    return setenv(name, text, 1);
}
static int inherited(void)
{
    int fd = descriptor("P0_FILE"), alias = descriptor("P0_ALIAS"), excluded = descriptor("P0_CLOEXEC");
    char a = 0, b = 0;
    errno = 0;
    if (fd < 3 || alias <= fd || excluded <= alias || read(fd, &a, 1) != 1 || a != 'B'
        || read(alias, &b, 1) != 1 || b != 'C' || lseek(fd, 0, SEEK_CUR) != 3
        || fcntl(excluded, F_GETFD) != -1 || errno != EBADF) return 21;
    if (close(fd) || close(alias)) return 22;
    return 0;
}
static int setup_files(void)
{
    int fd = open("/tests/input", O_RDONLY);
    int alias = fd < 0 ? -1 : dup(fd);
    int excluded = alias < 0 ? -1 : open("/tests/input", O_RDONLY | O_CLOEXEC);
    char byte = 0;
    if (fd < 3 || alias <= fd || excluded <= alias || read(fd, &byte, 1) != 1 || byte != 'A'
        || number_environment("P0_FILE", fd) || number_environment("P0_ALIAS", alias)
        || number_environment("P0_CLOEXEC", excluded)) return 23;
    return 0;
}
static int fixed_policy(void)
{
    const char *names[] = {NULL, "libc.so.0.1", "libmissing.so"};
    for (unsigned i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        (void)dlerror();
        if (dlopen(names[i], RTLD_NOW) != NULL) return 31;
        const char *error = dlerror();
        if (!error || !strstr(error, "XOS fixed closure") || dlerror() != NULL) return 32;
    }
    if (dlmopen(LM_ID_NEWLM, "libc.so.0.1", RTLD_NOW) != NULL) return 33;
    const char *error = dlerror();
    if (!error || !strstr(error, "XOS fixed closure") || dlerror() != NULL) return 34;
    if (dlclose((void *)1) != -1) return 35;
    error = dlerror();
    if (!error || !strstr(error, "XOS fixed closure") || dlerror() != NULL) return 36;
    puts("P0_PUBLIC_RUNTIME_LOAD_POLICY_OK");
    return 0;
}
int main(int argc, char **argv)
{
    if (argc != 2 || initialized != 19 || tls_value != 31 || relative_function() != 47) return 10;
    const char *environment = getenv("DYNAMIC_ENV");
    if (!environment || strcmp(environment, "verified")) return 11;
    if (!strcmp(argv[1], "basic")) {
        puts("P0_PUBLIC_C_OK constructor=1 tls=1 relocation=1 environment=1");
        return 0;
    }
    if (!strcmp(argv[1], "policy")) return fixed_policy();
    if (!strcmp(argv[1], "spawned")) {
        int error = inherited();
        if (!error) puts("P0_PUBLIC_SPAWN_CHILD_OK aliases=1 cloexec=1");
        return error;
    }
    if (!strcmp(argv[1], "replaced")) {
        if (getpid() != descriptor("P0_PID")) return 41;
        int error = inherited();
        if (!error) puts("P0_PUBLIC_EXEC_OK same_pid=1 aliases=1 cloexec=1");
        return error;
    }
    int error = setup_files();
    if (error) return error;
    if (!strcmp(argv[1], "spawn")) {
        if (unlink("/tests/constructor_ready") != 0 && errno != ENOENT) return 53;
        if (setenv("P0_READY_CONSTRUCTOR", "1", 1) != 0) return 54;
        char *arguments[] = {argv[0], "spawned", NULL};
        pid_t child = -1;
        int result = posix_spawn(&child, argv[0], NULL, NULL, arguments, environ);
        if (result || child <= 0) { printf("P0_SPAWN_ERROR=%d\n", result); return 42; }
        const int ready = open("/tests/constructor_ready", O_RDONLY | O_CLOEXEC);
        char completed[5];
        if (ready < 0 || read(ready, completed, sizeof(completed)) != 5
            || memcmp(completed, "READY", sizeof(completed)) || close(ready)
            || unlink("/tests/constructor_ready") || unsetenv("P0_READY_CONSTRUCTOR")) return 55;
        puts("P0_PUBLIC_READY_AFTER_CONSTRUCTORS");
        int status = -1;
        if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status)) return 43;
        char byte = 0;
        if (read(descriptor("P0_FILE"), &byte, 1) != 1 || byte != 'D'
            || !(fcntl(descriptor("P0_CLOEXEC"), F_GETFD) & FD_CLOEXEC)) return 44;
        close(descriptor("P0_FILE")); close(descriptor("P0_ALIAS")); close(descriptor("P0_CLOEXEC"));
        puts("P0_PUBLIC_SPAWN_OK ordinary_api=1 shared_cursor=1 wait_ready=1");
        return 0;
    }
    if (!strcmp(argv[1], "exec")) {
        const pid_t before = getpid();
        if (number_environment("P0_PID", before)) return 45;
        char *large = malloc(4097);
        if (!large) return 46;
        memset(large, 'x', 4096); large[4096] = 0;
        char *invalid[] = {argv[0], large, NULL};
        errno = 0;
        if (execve(argv[0], invalid, environ) != -1 || errno != E2BIG || getpid() != before
            || lseek(descriptor("P0_FILE"), 0, SEEK_CUR) != 1) return 47;
        free(large);
        puts("P0_PUBLIC_CANCEL_OK old_pid=1 old_descriptors=1");
        fflush(stdout);
        char *arguments[] = {argv[0], "replaced", NULL};
        execve(argv[0], arguments, environ);
        printf("P0_EXEC_ERROR=%d\n", errno);
        return 48;
    }
    return 49;
}
