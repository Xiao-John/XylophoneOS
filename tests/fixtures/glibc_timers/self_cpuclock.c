/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

#define REQUIRE(test) do { if (!(test)) { \
  printf ("SELF_CPUCLOCK_FAIL line=%d errno=%d\n", __LINE__, errno); return 1; \
} } while (0)
static unsigned long long ns (struct timespec value)
{
  return (unsigned long long) value.tv_sec * 1000000000 + value.tv_nsec;
}
int main (void)
{
  clockid_t zero, explicit_self, unchanged = 99;
  errno = EDOM;
  REQUIRE (clock_getcpuclockid (0, &zero) == 0 && errno == EDOM);
  REQUIRE (clock_getcpuclockid (getpid (), &explicit_self) == 0 && errno == EDOM);
  REQUIRE (zero == CLOCK_PROCESS_CPUTIME_ID && explicit_self == zero);
  REQUIRE (clock_getcpuclockid (getpid () + 1, &unchanged) == ENOSYS
           && unchanged == 99 && errno == EDOM);
  struct timespec start, stop, resolution;
  REQUIRE (clock_getres (zero, &resolution) == 0 && ns (resolution) > 0);
  REQUIRE (clock_gettime (zero, &start) == 0);
  volatile unsigned long sum = 0;
  for (unsigned long i = 0; i < 2000000; ++i) sum += i;
  REQUIRE (clock_gettime (explicit_self, &stop) == 0 && ns (stop) > ns (start));
  printf ("SELF_CPUCLOCK_PASS delta_ns=%llu resolution_ns=%llu sum=%lu\n",
          ns (stop) - ns (start), ns (resolution), sum);
  return 0;
}
