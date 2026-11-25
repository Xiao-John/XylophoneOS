/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <pthreadP.h>
#include <string.h>
#include "xos_thread_name.h"

static pthread_t current = 100;

pthread_t
__pthread_self (void)
{
  return current;
}

size_t
__strnlen (const char *name, size_t size)
{
  size_t length;
  for (length = 0; length < size && name[length] != '\0'; ++length)
    ;
  return length;
}

int __pthread_getname_np (pthread_t, char *, size_t);
int __pthread_setname_np (pthread_t, const char *);

int
main (void)
{
  const pthread_t child = 0x100000000UL;
  char name[16] = { 0 };
  assert (__pthread_getname_np (current, name, sizeof (name)) == 0);
  assert (strcmp (name, "main") == 0);
  assert (__pthread_setname_np (current, "creator") == 0);
  assert (__xos_thread_name_add (child) == 0);
  assert (__pthread_getname_np (child, name, sizeof (name)) == 0);
  assert (strcmp (name, "creator") == 0);
  assert (__pthread_setname_np (child, "1234567890123456") == ERANGE);
  assert (__pthread_getname_np (child, name, sizeof (name) - 1) == ERANGE);
  assert (strcmp (name, "creator") == 0);
  assert (__pthread_setname_np (child, "worker") == 0);
  current = child;
  assert (__pthread_getname_np (current, name, sizeof (name)) == 0);
  assert (strcmp (name, "worker") == 0);
  assert (__xos_thread_name_add (101) == 0);
  assert (__pthread_getname_np (101, name, sizeof (name)) == 0);
  assert (strcmp (name, "worker") == 0);
  assert (__xos_thread_name_add (102) == 0);
  assert (__xos_thread_name_add (103) == EAGAIN);
  assert (__pthread_setname_np (102, "") == 0);
  assert (__pthread_getname_np (102, name, sizeof (name)) == 0);
  assert (name[0] == '\0');
  __xos_thread_name_remove (child);
  current = 100;
  assert (__pthread_setname_np (child, "stale") == ESRCH);
  assert (__pthread_getname_np (child, name, sizeof (name)) == ESRCH);
  assert (__xos_thread_name_add (103) == 0);
  assert (__pthread_getname_np (103, name, sizeof (name)) == 0);
  assert (strcmp (name, "creator") == 0);
}
