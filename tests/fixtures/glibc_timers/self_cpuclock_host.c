/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

int __clock_getcpuclockid (pid_t, clockid_t *);
static int sample_error, pid_error, samples, pid_queries;
pid_t __getpid (void)
{
  ++pid_queries;
  if (pid_error != 0) { errno = pid_error; return -1; }
  return 123;
}
int __clock_getres (clockid_t clock, struct timespec *value)
{
  assert (clock == CLOCK_PROCESS_CPUTIME_ID);
  ++samples;
  if (sample_error != 0) { errno = sample_error; return -1; }
  *value = (struct timespec) {0, 1};
  return 0;
}
int main (void)
{
  clockid_t output = 91;
  errno = EDOM;
  assert (__clock_getcpuclockid (0, &output) == 0);
  assert (output == CLOCK_PROCESS_CPUTIME_ID && samples == 1 && pid_queries == 0);
  assert (__clock_getcpuclockid (123, &output) == 0 && samples == 2);
  output = 91;
  assert (__clock_getcpuclockid (124, &output) == ENOSYS && output == 91 && samples == 2);
  assert (__clock_getcpuclockid (-1, &output) == ESRCH && output == 91);
  assert (__clock_getcpuclockid (0, NULL) == EINVAL);
  for (unsigned i = 0; i < 4; ++i)
    {
      sample_error = (int[]) {ENOTSUP, EIO, ENOMEM, EOVERFLOW}[i];
      assert (__clock_getcpuclockid (0, &output) == sample_error && output == 91);
      assert (errno == EDOM);
    }
  pid_error = EOVERFLOW;
  assert (__clock_getcpuclockid (123, &output) == EOVERFLOW && output == 91);
  assert (errno == EDOM);
  puts ("SELF_CPUCLOCK_HOST_PASS cases=10 error_number errno output_preserved");
}
