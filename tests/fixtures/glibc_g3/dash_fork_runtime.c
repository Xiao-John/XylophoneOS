/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int stage;
static _Thread_local volatile int value = 41;
static void *stack_base;
static size_t stack_size;

static void before_fork(void) { stage = 1; }
static void in_parent(void) { stage = stage == 1 ? 2 : -1; }
static void in_child(void) { stage = stage == 1 ? 3 : -1; }

static int get_stack(pthread_t thread, void **base, size_t *size)
{
    pthread_attr_t attributes;
    if (pthread_getattr_np(thread, &attributes) != 0)
        return 0;
    const int result = pthread_attr_getstack(&attributes, base, size);
    return pthread_attr_destroy(&attributes) == 0 && result == 0;
}

static int inherited_thread(pthread_t parent_thread)
{
    const pthread_t tid = pthread_self();
    void *base;
    size_t size;
    char name[16];
    pthread_attr_t unavailable;
    return tid != parent_thread && pthread_gettid_np(tid) == (pid_t)tid
        && pthread_getname_np(tid, name, sizeof(name)) == 0 && strcmp(name, "fork-parent") == 0
        && get_stack(tid, &base, &size) && base == stack_base && size == stack_size
        && pthread_gettid_np(parent_thread) == -1
        && pthread_getname_np(parent_thread, name, sizeof(name)) == ESRCH
        && pthread_getattr_np(parent_thread, &unavailable) == ESRCH;
}

static int child_exited(pid_t pid, int code)
{
    int status = 0;
    if (waitpid(pid, &status, 0) == pid && WIFEXITED(status) && WEXITSTATUS(status) == code)
        return 1;
    fprintf(stderr, "DASH_GLIBC_FORK_WAIT expected=%d status=%d\n", code, status);
    return 0;
}

int main(void)
{
    if (chdir("/out") != 0 || pthread_atfork(before_fork, in_parent, in_child) != 0)
        return 100;
    const int file = open("fork-shared.txt", O_RDWR | O_CREAT | O_TRUNC, 0600);
    const int alias = dup(file);
    if (file < 0 || alias < 0 || write(file, "abc", 3) != 3 || lseek(alias, 0, SEEK_SET) != 0)
        return 101;
    const pid_t parent = getpid();
    const pthread_t parent_thread = pthread_self();
    if (pthread_setname_np(parent_thread, "fork-parent") != 0
        || !get_stack(parent_thread, &stack_base, &stack_size) || stack_size == 0)
        return 108;
    pid_t child = fork();
    if (child < 0)
        return 102;
    if (child == 0) {
        char first;
        char cwd[32];
        if (stage != 3) _Exit(110);
        if (value != 41 || getpid() == parent || pthread_self() == parent_thread) _Exit(111);
        if (getcwd(cwd, sizeof(cwd)) == NULL || strcmp(cwd, "/out") != 0) _Exit(112);
        if (read(alias, &first, 1) != 1 || first != 'a') _Exit(113);
        if (!inherited_thread(parent_thread)) _Exit(116);
        value = 42;
        _Exit(23);
    }
    char second;
    if (!child_exited(child, 23)) return 103;
    if (stage != 2 || value != 41 || pthread_self() != parent_thread) return 114;
    if (read(file, &second, 1) != 1 || second != 'b') return 115;
    child = _Fork();
    if (child < 0)
        return 105;
    if (child == 0)
        _Exit(stage == 2 && value == 41 && pthread_self() != parent_thread
              && inherited_thread(parent_thread) ? 29 : 106);
    if (!child_exited(child, 29) || stage != 2 || close(alias) != 0 || close(file) != 0)
        return 107;
    puts("DASH_GLIBC_FORK_RUNTIME_PASS tls=isolated alias=shared atfork=ordered name_stack=rebound");
    return 0;
}
