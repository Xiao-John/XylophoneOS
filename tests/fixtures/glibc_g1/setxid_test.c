/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
struct xid_command { unsigned long sentinel[4]; };
int __nptl_setxid (struct xid_command *);
void __nptl_setxid_sighandler (int, siginfo_t *, void *);
int main (void)
{
  struct xid_command cmd = {{11, 22, 33, 44}};
  errno = 0;
  if (__nptl_setxid (&cmd) != -1 || errno != ENOSYS) return 1;
  if (cmd.sentinel[0] != 11 || cmd.sentinel[1] != 22 ||
      cmd.sentinel[2] != 33 || cmd.sentinel[3] != 44) return 2;
  errno = 0;
  if (__nptl_setxid (0) != -1 || errno != ENOSYS) return 3;
  pid_t pid = fork ();
  if (pid == 0) { __nptl_setxid_sighandler (0, 0, 0); _exit (0); }
  int status;
  if (pid <= 0 || waitpid (pid, &status, 0) != pid || !WIFSIGNALED (status) ||
      (WTERMSIG (status) != SIGILL && WTERMSIG (status) != SIGTRAP)) return 4;
  return 0;
}
