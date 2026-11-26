/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
/* Appended to eval.c, with its upstream node/error declarations in scope. */
void xos_check_tree(union node *n);
#ifdef XOS_DASH_GLIBC_PREVIEW
int xos_has_heredoc(union node *n) {
    for (; n; n = n->nfile.next)
        if (n->type == NHERE || n->type == NXHERE) return 1;
    return 0;
}
#endif

static void xos_check_redirect(union node *n) {
    for (; n; n = n->nfile.next) {
        if (n->nfile.fd < 0 || n->nfile.fd > 2)
            sh_error("only descriptors 0, 1, and 2 are available in XOS dash B2");
        switch (n->type) {
        case NFROM: case NFROMTO: case NTO: case NCLOBBER: case NAPPEND:
            xos_check_tree(n->nfile.fname);
            break;
        case NTOFD: case NFROMFD:
            if (n->ndup.dupfd > 2)
                sh_error("only descriptors 0, 1, and 2 are available in XOS dash B2");
            break;
        case NHERE: case NXHERE:
            xos_check_tree(n->nhere.doc);
            break;
        default:
            sh_error("redirection form unavailable in XOS dash C3");
        }
    }
}

void xos_check_tree(union node *n) {
    if (!n) return;
    switch (n->type) {
    case NCMD:
        xos_check_redirect(n->ncmd.redirect);
        xos_check_tree(n->ncmd.assign); xos_check_tree(n->ncmd.args); break;
    case NARG:
        for (; n; n = n->narg.next) {
            struct nodelist *sub;
#ifdef XOS_DASH_GLIBC_PREVIEW
            if (n->narg.backquote) sh_error("command substitution unavailable in the glibc dash preview");
#endif
            for (sub = n->narg.backquote; sub; sub = sub->next) xos_check_tree(sub->n);
        }
        break;
    case NAND: case NOR: case NSEMI: case NWHILE: case NUNTIL:
        xos_check_tree(n->nbinary.ch1); xos_check_tree(n->nbinary.ch2); break;
    case NIF:
        xos_check_tree(n->nif.test); xos_check_tree(n->nif.ifpart);
        xos_check_tree(n->nif.elsepart); break;
    case NFOR:
        xos_check_tree(n->nfor.args); xos_check_tree(n->nfor.body); break;
    case NCASE:
        xos_check_tree(n->ncase.expr); xos_check_tree(n->ncase.cases); break;
    case NCLIST:
        for (; n; n = n->nclist.next) {
            xos_check_tree(n->nclist.pattern);
            xos_check_tree(n->nclist.body);
        }
        break;
    case NDEFUN:
        xos_check_tree(n->ndefun.body); break;
    case NREDIR:
#ifdef XOS_DASH_GLIBC_PREVIEW
        if (xos_has_heredoc(n->nredir.redirect))
            sh_error("here-document requires a parent builtin in the glibc dash preview");
#endif
        xos_check_tree(n->nredir.n); xos_check_redirect(n->nredir.redirect); break;
    case NNOT: xos_check_tree(n->nnot.com); break;
    case NPIPE: {
        struct nodelist *lp;
        unsigned count = 0;
        if (n->npipe.backgnd) sh_error("background pipeline unavailable in XOS dash C1");
        for (lp = n->npipe.cmdlist; lp; lp = lp->next) {
            if (++count > 4) sh_error("XOS dash C1 supports at most 4 pipeline stages");
            xos_check_tree(lp->n);
        }
        break;
    }
    case NSUBSHELL:
#ifdef XOS_DASH_GLIBC_PREVIEW
        sh_error("subshells unavailable in the glibc dash preview");
#endif
        xos_check_tree(n->nredir.n); xos_check_redirect(n->nredir.redirect); break;
    case NBACKGND: sh_error("background jobs unavailable in XOS dash B2");
    default: sh_error("construct unavailable in XOS dash B2");
    }
}

/* Only literal, assignment-free external stages can use the C1 direct spawn
 * path. Anything that can expand or alter Shell state runs after real fork. */
static int xos_literal_args(union node *n) {
    for (; n; n = n->narg.next) {
        const unsigned char *p = (const unsigned char *)n->narg.text;
        if (n->narg.backquote) return 0;
        for (; *p; ++p) if (*p >= 128) return 0;
    }
    return 1;
}
static int xos_direct_stage(union node *n) {
    struct cmdentry command;
    union node *r;
    if (n->type != NCMD || n->ncmd.assign || !n->ncmd.args || !xos_literal_args(n->ncmd.args)) return 0;
    for (r = n->ncmd.redirect; r; r = r->nfile.next) {
        switch (r->type) {
        case NFROM: case NFROMTO: case NTO: case NCLOBBER: case NAPPEND:
            if (!xos_literal_args(r->nfile.fname)) return 0;
            break;
        case NFROMFD: case NTOFD: if (r->ndup.vname) return 0; break;
        default: return 0;
        }
    }
    find_command(n->ncmd.args->narg.text, &command, 0, pathval());
    return command.cmdtype != CMDBUILTIN && command.cmdtype != CMDFUNCTION;
}
#ifdef XOS_DASH_GLIBC_PREVIEW
/* Literal printf can run in the parent after its consumers are runnable. */
static int xos_printf_stage(union node *n) {
    struct cmdentry command;
    if (n->type != NCMD || n->ncmd.assign || n->ncmd.redirect || !n->ncmd.args ||
        strcmp(n->ncmd.args->narg.text, "printf") != 0) return 0;
    for (union node *arg = n->ncmd.args->narg.next; arg; arg = arg->narg.next) {
        if (arg->narg.backquote) return 0;
        for (const unsigned char *p = (const unsigned char *)arg->narg.text; *p; ++p) {
            if (*p == (unsigned char)CTLESC && p[1] != 0) { ++p; continue; }
            if (*p == (unsigned char)CTLQUOTEMARK) continue;
            if (*p >= (unsigned char)CTL_FIRST && *p <= (unsigned char)CTL_LAST) return 0;
        }
    }
    find_command("printf", &command, 0, pathval());
    return command.cmdtype == CMDBUILTIN && command.u.cmd == PRINTFCMD;
}

static int xos_pipeline_printf(union node *n, int flags) {
    struct stackmark mark;
    struct arglist arguments = { .list = NULL, .lastp = &arguments.list };
    setstackmark(&mark);
    for (union node *arg = n->ncmd.args; arg; arg = arg->narg.next)
        expandarg(arg, &arguments, EXP_FULL | EXP_TILDE);
    int argc = 0;
    for (struct strlist *arg = arguments.list; arg; arg = arg->next) ++argc;
    char **argv = stalloc((argc + 1) * sizeof(*argv));
    int at = 0;
    for (struct strlist *arg = arguments.list; arg; arg = arg->next) argv[at++] = arg->text;
    argv[at] = NULL;
    int error = evalbltin(PRINTFCMD, argc, argv, flags);
    popstackmark(&mark);
    return error ? 2 : exitstatus;
}
#endif
/* Run the normal argument/assignment/redirection evaluator for each external
 * stage. Only vforkexec changes mode: launch now, collect after ALL launches.
 * Saved descriptors and the upstream unwind stacks cover every error path. */
int xos_evalpipe(union node *n, int flags) {
    struct jmploc loc;
    struct jmploc *savehandler = handler;
    struct localvar_list *locals = pushlocalvars(0);
    struct parsefile *files = parsefile;
    struct redirtab *redirs = pushredir(NULL);
    struct nodelist *lp;
    static int saved[2], pip[2], previous;
    int caught, status = 125, fd;
    const int before_status = exitstatus;
#ifdef XOS_DASH_GLIBC_PREVIEW
    static int producer;
    int producer_status = 0;
    producer = -1;
#endif
    saved[0] = saved[1] = -2; pip[0] = pip[1] = previous = -1;
    caught = setjmp(loc.loc);
    if (!caught) {
        handler = &loc;
        xos_pipeline_begin();
        for (fd = 0; fd < 2; ++fd) {
            /* Three states: >=0 saved copy; -1 was closed before the pipeline
               (EBADF); -2 untouched - a real fcntl failure must keep -2 so the
               restore never treats "save failed" as "originally closed" and
               closes a live descriptor (stdout) on the longjmp path. */
            int duped = fcntl(fd, F_DUPFD_CLOEXEC, 10);
            if (duped >= 0) saved[fd] = duped;
            else if (errno == EBADF) saved[fd] = -1;
            else sh_error("pipeline: save descriptor");
        }
        for (lp = n->npipe.cmdlist; lp; lp = lp->next) {
            if (lp->next) {
#ifdef XOS_DASH_GLIBC_PREVIEW
                if (pipe2(pip, O_CLOEXEC) < 0) sh_error("pipeline: pipe: %s", strerror(errno));
#else
                if (pipe(pip) < 0) sh_error("pipeline: pipe: %s", strerror(errno));
#endif
                // Closed stdio slots may be reused by pipe(); keep both ends
                // away from dup2's destinations before installing any route.
                for (fd = 0; fd < 2; ++fd) {
                    if (pip[fd] > 2) continue;
                    int moved = fcntl(pip[fd], F_DUPFD_CLOEXEC, 3);
                    if (moved < 0) sh_error("pipeline: save pipe descriptor");
                    close(pip[fd]);
                    pip[fd] = moved;
                }
            }
            if (previous >= 0 && dup2(previous, 0) < 0) sh_error("pipeline: stdin");
            if (pip[1] >= 0 && dup2(pip[1], 1) < 0) sh_error("pipeline: stdout");
            exitstatus = before_status;
#ifdef XOS_DASH_GLIBC_PREVIEW
            if (lp == n->npipe.cmdlist && xos_printf_stage(lp->n)) {
                producer = pip[1];
                pip[1] = -1;
                status = 0;
            } else
#endif
            if (xos_direct_stage(lp->n)) {
                status = evalcommand(lp->n, 0);
            } else {
                // C1 pipelines run external commands only: a builtin stage
                // (printf, cd, ...) is rejected before it can run, and the
                // longjmp path cancels the stages already started.
                if (lp->n->type == NCMD && lp->n->ncmd.args && !lp->n->ncmd.assign) {
                    struct cmdentry builtin_stage;
                    find_command(lp->n->ncmd.args->narg.text, &builtin_stage, 0, pathval());
                    if (builtin_stage.cmdtype == CMDBUILTIN || builtin_stage.cmdtype == CMDFUNCTION)
                        sh_error("C1 pipeline requires external commands");
                }
                if (forkshell(NULL, lp->n, FORK_FG) == 0) {
                    /* previous/pip[1] may be the very stdio slot they were
                       dup'd into when the original stdio was closed (e.g.
                       previous == 0 is this stage's live stdin): closing the
                       number would kill the live endpoint. Copies in slots
                       above 2 are always safe to drop. */
                    if (previous > 0) close(previous);
                    if (pip[0] >= 0) close(pip[0]);
                    if (pip[1] > 0) close(pip[1]);
                    for (fd = 0; fd < 2; ++fd) if (saved[fd] >= 0) close(saved[fd]);
                    evaltreenr(lp->n, (flags & EV_TESTED) | EV_EXIT);
                }
                status = xos_pipeline_failed ? 137 : 0;
            }
            unwindredir(redirs); unwindfiles(files); unwindlocalvars(locals);
            for (fd = 0; fd < 2; ++fd) {
                if (saved[fd] >= 0) { dup2(saved[fd], fd); }
                /* Never close a slot that still holds an active pipeline
                   endpoint: with a closed stdin, pipe() legitimately takes
                   fd0 and the next stage needs it as previous/stdin. The
                   explicit pip/previous closes below release it instead. */
                else if (saved[fd] == -1 && fd != pip[0] && fd != pip[1]) close(fd);
            }
            if (previous >= 0) close(previous);
            previous = -1;
            if (pip[1] >= 0) close(pip[1]);
            pip[1] = -1;
            previous = pip[0]; pip[0] = -1;
            if (xos_pipeline_failed || status) break;
        }
#ifdef XOS_DASH_GLIBC_PREVIEW
        if (producer >= 0 && !xos_pipeline_failed && !status) {
            if (dup2(producer, 1) < 0) sh_error("pipeline: printf stdout");
            close(producer);
            producer = -1;
            producer_status = xos_pipeline_printf(n->npipe.cmdlist->n, flags);
        }
#endif
    }
    handler = savehandler;
    unwindredir(redirs); unwindfiles(files); unwindlocalvars(locals);
    for (fd = 0; fd < 2; ++fd) {
        if (saved[fd] >= 0) { dup2(saved[fd], fd); close(saved[fd]); }
        else if (saved[fd] == -1) close(fd);
    }
    if (previous >= 0) close(previous);
    if (pip[0] >= 0) close(pip[0]);
    if (pip[1] >= 0) close(pip[1]);
#ifdef XOS_DASH_GLIBC_PREVIEW
    if (producer >= 0) close(producer);
#endif
    if (caught || xos_pipeline_failed || status) {
        int failure = caught ? 2 : status;
        xos_pipeline_finish(1);
        if (caught) longjmp(handler->loc, 1);
        return failure;
    }
    int result = xos_pipeline_finish(0);
#ifdef XOS_DASH_GLIBC_PREVIEW
    if (pipefail && result == 0) return producer_status;
#endif
    return result;
}
