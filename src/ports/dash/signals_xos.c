/* SPDX-License-Identifier: Apache-2.0 */
/* Shell-local hooks only: this profile has no asynchronous signal delivery.
 * These do not replace or export libc signal APIs. Signal builtins fail. */
#include <signal.h>
#include <stdlib.h>
#include "shell.h"
#include "nodes.h"
#include "eval.h"
#include "output.h"
#include "error.h"
#include "trap.h"
int trapcnt;
char sigmode[NSIG];
volatile sig_atomic_t pending_sig, gotsigchld;
void setsignal(int signo) { (void)signo; }
void ignoresig(int signo) { (void)signo; }
void setinteractive(int enabled) { (void)enabled; }
void dotrap(void) { }
void onsig(int signo) { sh_error("unexpected signal hook"); }
int decode_signal(const char *name, int minimum) { return -1; }
void sigblockall(sigset_t *oldmask) { if (oldmask) *oldmask = 0; }
int trapcmd(int argc, char **argv) { sh_error("trap unavailable in XOS dash A"); }
void exitshell(void) { flushall(); exit(exitstatus & 255); }
