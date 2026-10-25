/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
/* Appended to eval.c, with its upstream node/error declarations in scope. */
void xos_check_tree(union node *n);
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
        default:
            sh_error("redirection form unavailable in XOS dash B2");
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
    saved[0] = saved[1] = -2; pip[0] = pip[1] = previous = -1;
    caught = setjmp(loc.loc);
    if (!caught) {
        handler = &loc;
        xos_pipeline_begin();
        for (fd = 0; fd < 2; ++fd) {
            saved[fd] = fcntl(fd, F_DUPFD_CLOEXEC, 10);
            if (saved[fd] < 0 && errno != EBADF) sh_error("pipeline: save descriptor");
        }
        for (lp = n->npipe.cmdlist; lp; lp = lp->next) {
            if (lp->next && pipe(pip) < 0) sh_error("pipeline: pipe: %s", strerror(errno));
            if (previous >= 0 && dup2(previous, 0) < 0) sh_error("pipeline: stdin");
            if (pip[1] >= 0 && dup2(pip[1], 1) < 0) sh_error("pipeline: stdout");
            exitstatus = before_status;
            if (xos_direct_stage(lp->n)) {
                status = evalcommand(lp->n, 0);
            } else {
                if (forkshell(NULL, lp->n, FORK_FG) == 0) {
                    if (previous >= 0) close(previous);
                    if (pip[0] >= 0) close(pip[0]);
                    if (pip[1] >= 0) close(pip[1]);
                    for (fd = 0; fd < 2; ++fd) if (saved[fd] >= 0) close(saved[fd]);
                    evaltreenr(lp->n, (flags & EV_TESTED) | EV_EXIT);
                }
                status = xos_pipeline_failed ? 137 : 0;
            }
            unwindredir(redirs); unwindfiles(files); unwindlocalvars(locals);
            for (fd = 0; fd < 2; ++fd) {
                if (saved[fd] >= 0) dup2(saved[fd], fd); else close(fd);
            }
            if (previous >= 0) close(previous);
            previous = -1;
            if (pip[1] >= 0) close(pip[1]);
            pip[1] = -1;
            previous = pip[0]; pip[0] = -1;
            if (xos_pipeline_failed || status) break;
        }
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
    if (caught || xos_pipeline_failed || status) {
        int failure = caught ? 2 : status;
        xos_pipeline_finish(1);
        if (caught) longjmp(handler->loc, 1);
        return failure;
    }
    return xos_pipeline_finish(0);
}
