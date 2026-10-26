/* SPDX-License-Identifier: Apache-2.0 */
/* Bounded foreground spawn/fork backend. No asynchronous signals or background jobs. */
#include <errno.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include <fcntl.h>
#include "shell.h"
#include "nodes.h"
#include "jobs.h"
#include "exec.h"
#include "var.h"
#include "memalloc.h"
#include "output.h"
#include "eval.h"
#include "error.h"
#include "input.h"
#include "init.h"
#include "main.h"
#include "options.h"

int xos_pipeline_active, xos_pipeline_failed;
static int pipeline_children[4], pipeline_count;
void xos_pipeline_begin(void) {
    pipeline_count = 0; xos_pipeline_failed = 0; xos_pipeline_active = 1;
    if (xos_shell_foreground(NULL, 0, 1) < 0) sh_error("pipeline: foreground begin");
}
int xos_pipeline_finish(int aborting) {
    int i, status, result = 125, cancelled = 0, failed_status = 0;
    xos_pipeline_active = 0;
    if (!aborting && xos_shell_foreground(pipeline_children, pipeline_count, 1) < 0)
        aborting = cancelled = 1;
    for (i = 0; i < pipeline_count; ++i) {
        if (aborting) xos_shell_cancel(pipeline_children[i]);
    }
    for (i = 0; i < pipeline_count; ++i) {
        if (waitpid(pipeline_children[i], &status, 0) < 0) { result = 125; continue; }
        result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
        if (result) failed_status = result;
    }
    xos_shell_foreground(NULL, 0, 0);
    pipeline_count = 0;
    return cancelled ? 137 : aborting ? 125 : pipefail && failed_status ? failed_status : result;
}
pid_t backgndpid;
int job_warning, vforked;
int stoppedjobs(void) { return 0; }
void showjobs(struct output *out, int mode) { (void)out; (void)mode; }
int jobscmd(int argc, char **argv) { sh_error("jobs unavailable in XOS dash B2"); }
int waitcmd(int argc, char **argv) { sh_error("wait unavailable in XOS dash B2"); }
int killcmd(int argc, char **argv) { sh_error("signals unavailable in XOS dash B2"); }
struct xos_job { struct job job; unsigned capacity; int capture_fd; struct xos_job *next; };
static struct xos_job *all_jobs;
static void free_job(struct job *job) {
    struct xos_job **link = &all_jobs;
    while (*link && &(*link)->job != job) link = &(*link)->next;
    if (*link) {
        struct xos_job *owned = *link;
        *link = owned->next; free(owned->job.ps); free(owned);
    }
}
void xos_job_capture(struct job *job, int fd) {
    ((struct xos_job *)job)->capture_fd = fd;
}
void xos_jobs_cleanup(void) {
    while (all_jobs) {
        unsigned i;
        struct job *job = &all_jobs->job;
        if (all_jobs->capture_fd >= 0) close(all_jobs->capture_fd);
        for (i = 0; i < job->nprocs; ++i) xos_shell_cancel(job->ps[i].pid);
        for (i = 0; i < job->nprocs; ++i) waitpid(job->ps[i].pid, NULL, 0);
        free_job(job);
    }
    if (xos_pipeline_active) xos_pipeline_finish(1);
    xos_shell_foreground(NULL, 0, 0);
}
#ifdef mkinit
RESET {
    xos_jobs_cleanup();
}
EXITRESET {
    xos_jobs_cleanup();
}
#endif
struct job *makejob(int count) {
    struct xos_job *owned;
    if (count < 1 || count > 4 || all_jobs) sh_error("XOS isolated job capacity");
    owned = calloc(1, sizeof(*owned));
    if (!owned) sh_error("isolated job allocation");
    owned->job.ps = calloc(count, sizeof(struct procstat));
    if (!owned->job.ps) { free(owned); sh_error("isolated job allocation"); }
    owned->capacity = count; owned->capture_fd = -1; owned->job.used = 1;
    all_jobs = owned;
    if (xos_shell_foreground(NULL, 0, 1) < 0) { free_job(&owned->job); sh_error("isolated foreground"); }
    return &owned->job;
}
int forkshell(struct job *job, union node *node, int mode) {
    int child;
    if (mode == FORK_BG || (!job && !xos_pipeline_active)) sh_error("untracked child unavailable");
    flushall(); flush_input();
    child = fork();
    if (child < 0) {
        if (job) { free_job(job); xos_shell_foreground(NULL, 0, 0); }
        sh_error("fork: %s", strerror(errno));
    }
    if (!child) {
        mypid = 0; shlvl++;
        xos_pipeline_active = xos_pipeline_failed = pipeline_count = 0;
        while (all_jobs) free_job(&all_jobs->job);
        forkreset(mode == FORK_NOJOB ? node : NULL);
        return 0;
    }
    if (job) {
        unsigned i;
        int children[4];
        if (job->nprocs >= ((struct xos_job *)job)->capacity) {
            xos_shell_cancel(child); waitpid(child, NULL, 0); sh_error("isolated job capacity");
        }
        job->ps[job->nprocs++].pid = child;
        for (i = 0; i < job->nprocs; ++i) children[i] = job->ps[i].pid;
        if (xos_shell_foreground(children, job->nprocs, 1) < 0) {
            for (i = 0; i < job->nprocs; ++i) xos_shell_cancel(children[i]);
        }
    } else {
        if (pipeline_count >= 4) { xos_shell_cancel(child); waitpid(child, NULL, 0); sh_error("pipeline capacity"); }
        pipeline_children[pipeline_count++] = child;
        if (xos_shell_foreground(pipeline_children, pipeline_count, 1) < 0) xos_pipeline_failed = 1;
    }
    return child;
}

static int xos_is_gnu_driver(const char *path) {
    const char *name = strrchr(path, '/');
    name = name ? name + 1 : path;
    return !strcmp(name, "x86_64-elf-gcc") || !strcmp(name, "x86_64-elf-g++") ||
           !strcmp(name, "gcc") || !strcmp(name, "g++");
}

static int xos_is_make(const char *path) {
    const char *name = strrchr(path, '/'); name = name ? name + 1 : path;
    return !strcmp(name, "make");
}
int xos_shell_script(const char *path) {
    char data[256]; int fd = open(path, O_RDONLY | O_CLOEXEC); ssize_t n; unsigned i;
    if (fd < 0) return 0;
    n = read(fd, data, sizeof(data)); close(fd);
    if (n < 0) return 0;
    for (i = 0; i < (unsigned)n; ++i) if (!data[i]) return 0;
    if (n >= 2 && data[0] == '#' && data[1] == '!') {
        unsigned start = 2, end;
        while (start < (unsigned)n && (data[start] == ' ' || data[start] == '\t')) ++start;
        end = start;
        while (end < (unsigned)n && data[end] != ' ' && data[end] != '\t' && data[end] != '\n' && data[end] != '\r') ++end;
        if (!((end-start == 7 && !memcmp(data+start,"/bin/sh",7)) ||
              (end-start == 9 && !memcmp(data+start,"/bin/dash",9)) ||
              (end-start == 13 && !memcmp(data+start,"/usr/bin/dash",13)))) return 0;
        while (end < (unsigned)n && (data[end] == ' ' || data[end] == '\t')) ++end;
        if (end == sizeof(data) || (end < (unsigned)n && data[end] != '\n' && data[end] != '\r')) return 0;
    }
    return 1;
}
int xos_shell_execve(const char *path, char *const argv[], char *const envp[]) {
    if (xos_is_gnu_driver(path)) return xos_execve_driver(path, argv, envp);
    if (xos_is_make(path)) return xos_execve_make(path, argv, envp);
    return execve(path, argv, envp);
}
static int xos_spawn(pid_t *child, const char *path, char **argv, char **envp) {
    int error = xos_is_gnu_driver(path)
        ? xos_posix_spawn_driver(child, path, NULL, NULL, argv, envp)
        : xos_is_make(path) ? xos_posix_spawn_make(child, path, NULL, NULL, argv, envp)
        : posix_spawn(child, path, NULL, NULL, argv, envp);
    if (error == ENOEXEC && xos_shell_script(path)) {
        char *script[65]; unsigned argc = 0;
        script[0] = "/usr/bin/dash"; script[1] = (char *)path;
        while (argv[argc]) { if (argc >= 62) return E2BIG; ++argc; }
        for (unsigned i = 1; i < argc; ++i) script[i+1] = argv[i];
        script[argc+1] = NULL;
        *child = fork();
        if (*child < 0) return errno;
        if (!*child) { execve(script[0], script, envp); _exit(errno == ENOENT ? 127 : 126); }
        return 0;
    }
    return error;
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
    unsigned i;
    int status, result = exitstatus;
    if (!job) return result;
    for (i = 0; i < job->nprocs; ++i) {
        if (waitpid(job->ps[i].pid, &status, 0) < 0) { result = 125; continue; }
        result = WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
    }
    free_job(job); xos_shell_foreground(NULL, 0, 0);
    return result;
}
