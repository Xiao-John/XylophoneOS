/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <limits.h>
static long result;
long __xos_getpid_test_trap (void) { return result; }
int __getpid (void);
int main (void)
{
  result = 1; errno = 7; assert (__getpid () == 1 && errno == 7);
  result = INT_MAX; assert (__getpid () == INT_MAX && errno == 7);
  result = (long) INT_MAX + 1; assert (__getpid () == -1 && errno == EOVERFLOW);
  result = 0; assert (__getpid () == -1 && errno == EIO);
  result = -1; assert (__getpid () == -1 && errno == EIO);
}
