# SPDX-License-Identifier: Apache-2.0
"""Run the actual dash pipeline FD orchestration on real host pipes.

The two external stages are bounded write/read callbacks; parsing, launching
processes and redirection unwinding are not exercised by this host regression.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

repo_root = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=repo_root / "src/ports/dash/admission_xos.c")
    args = parser.parse_args()
    implementation = args.source.read_text()
    implementation = implementation[implementation.index("int xos_evalpipe(union node *n, int flags) {"):]
    program = r'''
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
union node;
struct nodelist { union node *n; struct nodelist *next; };
union node {
    int type;
    struct { int type; union node *args, *assign; } ncmd;
    struct { int type; struct nodelist *cmdlist; } npipe;
    struct { int type; char *text; } narg;
};
struct jmploc { jmp_buf loc; };
struct localvar_list { int unused; };
struct parsefile { int unused; };
struct redirtab { int unused; };
struct cmdentry { int cmdtype; };
enum { NCMD, CMDBUILTIN, CMDFUNCTION, FORK_FG, EV_TESTED, EV_EXIT };
static struct jmploc *handler;
static struct parsefile *parsefile;
static int exitstatus, xos_pipeline_failed, stages;
static struct localvar_list locals;
static struct redirtab redirs;
static struct localvar_list *pushlocalvars(int ignored) { (void)ignored; return &locals; }
static struct redirtab *pushredir(void *ignored) { (void)ignored; return &redirs; }
static void unwindredir(struct redirtab *ignored) { (void)ignored; }
static void unwindfiles(struct parsefile *ignored) { (void)ignored; }
static void unwindlocalvars(struct localvar_list *ignored) { (void)ignored; }
static void xos_pipeline_begin(void) {}
static int xos_pipeline_finish(int aborting) { return aborting ? 125 : 0; }
static int xos_direct_stage(union node *ignored) { (void)ignored; return 1; }
static void find_command(const char *name, struct cmdentry *out, int flags, const char *path) {
    (void)name; (void)flags; (void)path; out->cmdtype = 99;
}
static const char *pathval(void) { return ""; }
static int forkshell(void *job, union node *node, int mode) {
    (void)job; (void)node; (void)mode; abort();
}
static void evaltreenr(union node *node, int flags) { (void)node; (void)flags; abort(); }
static void sh_error(const char *message, ...) {
    (void)message;
    longjmp(handler->loc, 1);
}
static int evalcommand(union node *node, int flags) {
    (void)node; (void)flags;
    if (stages++ == 0) {
        assert(write(1, "pipe-data", 9) == 9);
    } else {
        char buffer[16];
        assert(read(0, buffer, sizeof(buffer)) == 9);
        assert(memcmp(buffer, "pipe-data", 9) == 0);
    }
    return 0;
}
#include "pipeline.inc"
int main(int argc, char **argv) {
    assert(argc == 2);
    int closed = atoi(argv[1]);
    int null = open("/dev/null", O_RDWR);
    assert(null >= 0 && dup2(null, 0) == 0 && dup2(null, 1) == 1);
    if (null > 2) assert(close(null) == 0);
    if (closed & 1) assert(close(0) == 0);
    if (closed & 2) assert(close(1) == 0);
    assert(signal(SIGPIPE, SIG_IGN) != SIG_ERR);
    int existing[32];
    for (int fd = 3; fd < 32; ++fd) existing[fd] = fcntl(fd, F_GETFD) >= 0;
    union node first = {0}, second = {0}, pipeline = {0};
    struct nodelist tail = {&second, 0}, head = {&first, &tail};
    pipeline.npipe.cmdlist = &head;
    struct jmploc outer;
    handler = &outer;
    assert(setjmp(outer.loc) == 0);
    assert(xos_evalpipe(&pipeline, 0) == 0 && stages == 2);
    assert((fcntl(0, F_GETFD) < 0) == !!(closed & 1));
    assert((fcntl(1, F_GETFD) < 0) == !!(closed & 2));
    for (int fd = 3; fd < 32; ++fd) assert((fcntl(fd, F_GETFD) >= 0) == existing[fd]);
}
'''
    with tempfile.TemporaryDirectory(prefix="xos_dash_pipe_") as temporary:
        directory = Path(temporary)
        (directory / "pipeline.inc").write_text(implementation)
        source = directory / "test.c"
        source.write_text(program)
        binary = directory / "pipeline_test"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c99", "-D_DEFAULT_SOURCE",
                        "-Wall", "-Wextra", "-Werror", "-I", str(directory),
                        str(source), "-o", str(binary)], check=True)
        for closed in range(4):
            subprocess.run([str(binary), str(closed)], check=True)
    print("PASS dash pipeline: stdin/stdout open or closed, pipe content and descriptor restoration")


if __name__ == "__main__":
    main()
