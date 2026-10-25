/* SPDX-License-Identifier: Apache-2.0 */
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
    case NREDIR:
        xos_check_tree(n->nredir.n); xos_check_redirect(n->nredir.redirect); break;
    case NNOT: xos_check_tree(n->nnot.com); break;
    case NPIPE: sh_error("pipeline unavailable in XOS dash B2");
    case NSUBSHELL: sh_error("subshell unavailable in XOS dash B2");
    case NBACKGND: sh_error("background jobs unavailable in XOS dash B2");
    default: sh_error("construct unavailable in XOS dash B2");
    }
}
