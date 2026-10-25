/* SPDX-License-Identifier: Apache-2.0 */
/* Synchronous simple-command backend. No fork, signals or background jobs. */
#include <errno.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include "shell.h"
#include "nodes.h"
#include "jobs.h"
#include "exec.h"
#include "var.h"
#include "memalloc.h"
#include "output.h"
#include "eval.h"
#include "error.h"

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
