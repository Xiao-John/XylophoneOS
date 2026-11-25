/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <pthreadP.h>
#include <lowlevellock.h>
#include <string.h>
#include "xos_thread_name.h"

struct thread_name
{
  xos_u64 tid;
  char name[XOS_THREAD_NAME_SIZE];
};

/* The kernel allows up to four threads per process. Store values here
   so name readers never dereference a kernel-owned TCB after reaping. */
static struct thread_name names[4];
static int names_lock;

static struct thread_name *
find_name (xos_u64 tid)
{
  if (tid != 0)
    for (unsigned int i = 0; i < sizeof (names) / sizeof (names[0]); ++i)
      if (names[i].tid == tid)
        return &names[i];
  return NULL;
}

static struct thread_name *
add_name (xos_u64 tid, const char *name)
{
  for (unsigned int i = 0; i < sizeof (names) / sizeof (names[0]); ++i)
    if (names[i].tid == 0)
      {
        names[i].tid = tid;
        memcpy (names[i].name, name, XOS_THREAD_NAME_SIZE);
        return &names[i];
      }
  return NULL;
}

static struct thread_name *
current_name (xos_u64 self)
{
  static const char initial[XOS_THREAD_NAME_SIZE] = "main";
  struct thread_name *entry = find_name (self);
  return entry != NULL ? entry : add_name (self, initial);
}

int
__xos_thread_name_add (xos_u64 tid)
{
  xos_u64 self = __pthread_self ();
  lll_lock (names_lock, LLL_PRIVATE);
  struct thread_name *parent = current_name (self);
  struct thread_name *entry = parent == NULL ? NULL : add_name (tid, parent->name);
  lll_unlock (names_lock, LLL_PRIVATE);
  return entry == NULL ? EAGAIN : 0;
}

void
__xos_thread_name_remove (xos_u64 tid)
{
  lll_lock (names_lock, LLL_PRIVATE);
  struct thread_name *entry = find_name (tid);
  if (entry != NULL)
    entry->tid = 0;
  lll_unlock (names_lock, LLL_PRIVATE);
}

int
__xos_thread_name_get (xos_u64 tid, char *output)
{
  xos_u64 self = __pthread_self ();
  lll_lock (names_lock, LLL_PRIVATE);
  struct thread_name *entry = tid == self ? current_name (self) : find_name (tid);
  if (entry != NULL)
    memcpy (output, entry->name, XOS_THREAD_NAME_SIZE);
  lll_unlock (names_lock, LLL_PRIVATE);
  return entry == NULL ? (tid == self ? EAGAIN : ESRCH) : 0;
}

int
__xos_thread_name_set (xos_u64 tid, const char *name, unsigned long length)
{
  xos_u64 self = __pthread_self ();
  lll_lock (names_lock, LLL_PRIVATE);
  struct thread_name *entry = tid == self ? current_name (self) : find_name (tid);
  if (entry != NULL)
    {
      memcpy (entry->name, name, length);
      memset (entry->name + length, 0, XOS_THREAD_NAME_SIZE - length);
    }
  lll_unlock (names_lock, LLL_PRIVATE);
  return entry == NULL ? (tid == self ? EAGAIN : ESRCH) : 0;
}
