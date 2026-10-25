/* SPDX-License-Identifier: Apache-2.0 */
/* Synchronous simple-command backend. No fork, signals or background jobs. */
#include <errno.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include "shell.h"
#include "nodes.h"
#include "jobs.h"
#include "exec.h"
#include "var.h"
#include "memalloc.h"
#include "output.h"
#include "eval.h"
#include "error.h"

int xos_pipeline_active, xos_pipeline_failed;
static int pipeline_children[4], pipeline_count;
void xos_pipeline_begin(void) {
    pipeline_count = 0; xos_pipeline_failed = 0; xos_pipeline_active = 1;
    if (xos_shell_foreground(NULL, 0, 1) < 0) sh_error("pipeline: foreground begin");
}
int xos_pipeline_finish(int aborting) {
    int i, status, result = 125, cancelled = 0;
    xos_pipeline_active = 0;
    if (!aborting && xos_shell_foreground(pipeline_children, pipeline_count, 1) < 0)
        aborting = cancelled = 1;
    for (i = 0; i < pipeline_count; ++i) {
        if (aborting) xos_shell_cancel(pipeline_children[i]);
    }
    for (i = 0; i < pipeline_count; ++i) {
        if (waitpid(pipeline_children[i], &status, 0) < 0) { result = 125; continue; }
        result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    }
    xos_shell_foreground(NULL, 0, 0);
    pipeline_count = 0;
    return cancelled ? 137 : aborting ? 125 : result;
}
pid_t backgndpid;
int job_warning, vforked;
int stoppedjobs(void) { return 0; }
void showjobs(struct output *out, int mode) { (void)out; (void)mode; }
int jobscmd(int argc, char **argv) { sh_error("jobs unavailable in XOS dash B2"); }
int waitcmd(int argc, char **argv) { sh_error("wait unavailable in XOS dash B2"); }
int killcmd(int argc, char **argv) { sh_error("signals unavailable in XOS dash B2"); }
struct job *makejob(int count) { sh_error("isolated commands unavailable in XOS dash B2"); }
int forkshell(struct job *job, union node *node, int mode) {
    sh_error("fork unavailable in XOS dash B2");
}

static int xos_is_gnu_driver(const char *path) {
    const char *name = strrchr(path, '/');
    name = name ? name + 1 : path;
    return !strcmp(name, "x86_64-elf-gcc") || !strcmp(name, "x86_64-elf-g++") ||
           !strcmp(name, "gcc") || !strcmp(name, "g++");
}

static int xos_spawn(pid_t *child, const char *path, char **argv, char **envp) {
    return xos_is_gnu_driver(path)
        ? xos_posix_spawn_driver(child, path, NULL, NULL, argv, envp)
        : posix_spawn(child, path, NULL, NULL, argv, envp);
}

struct job *vforkexec(union node *node, char **argv, const char *path, int idx) {
    pid_t child;
    char **envp = environment();
    int error = ENOENT, saved_error = ENOENT, status;
    (void)node;
    flushall();
    if (strchr(argv[0], '/')) {
        error = xos_spawn(&child, argv[0], argv, envp);
    } else {
        while (padvance(&path, argv[0]) >= 0) {
            if (--idx >= 0 || pathopt != NULL) continue;
            error = xos_spawn(&child, stackblock(), argv, envp);
            if (!error) break;
            if (error != ENOENT && error != ENOTDIR) saved_error = error;
        }
        if (error && saved_error != ENOENT) error = saved_error;
    }
    if (error) {
        sh_warnx("%s: %s", argv[0], strerror(error));
        exitstatus = (error == ENOENT || error == ENOTDIR) ? 127 : 126;
        if (xos_pipeline_active) xos_pipeline_failed = 1;
    } else if (xos_pipeline_active) {
        if (pipeline_count >= 4) { xos_shell_cancel(child); waitpid(child, &status, 0); sh_error("pipeline limit"); }
        pipeline_children[pipeline_count++] = child;
        exitstatus = 0;
        if (xos_shell_foreground(pipeline_children, pipeline_count, 1) < 0) {
            xos_pipeline_failed = 1; exitstatus = 137;
        }
    } else if (waitpid(child, &status, 0) < 0) {
        sh_warnx("wait: %s", strerror(errno));
        exitstatus = 125;
    } else {
        exitstatus = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    }
    return NULL;
}
int waitforjob(struct job *job) {
    if (job) sh_error("unexpected job in XOS dash B2");
    return exitstatus;
}
