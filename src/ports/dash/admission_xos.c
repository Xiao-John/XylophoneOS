/* SPDX-License-Identifier: Apache-2.0 */
/* Appended to eval.c, with its upstream node/error declarations in scope. */
void xos_check_tree(union node *n) {
    if (!n) return;
    switch (n->type) {
    case NCMD:
        if (n->ncmd.redirect) sh_error("redirection unavailable in XOS dash B1");
        xos_check_tree(n->ncmd.assign); xos_check_tree(n->ncmd.args); break;
    case NARG:
        for (; n; n = n->narg.next)
            if (n->narg.backquote) sh_error("command substitution unavailable in XOS dash B1");
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
    case NNOT: xos_check_tree(n->nnot.com); break;
    case NPIPE: sh_error("pipeline unavailable in XOS dash B1");
    case NSUBSHELL: sh_error("subshell unavailable in XOS dash B1");
    case NBACKGND: sh_error("background jobs unavailable in XOS dash B1");
    case NREDIR: sh_error("redirection unavailable in XOS dash B1");
    default: sh_error("construct unavailable in XOS dash B1");
    }
}
