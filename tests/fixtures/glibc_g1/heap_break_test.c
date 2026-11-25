/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>

#include "xos_heap_break.h"

int __brk (void *);
void *_dl_early_allocate (size_t);
extern void *__curbrk;

static unsigned long int kernel_break = XOS_HEAP_BEGIN;
static unsigned long int requested;
static long int failure;
static unsigned int calls;

long int
__xos_heap_test_trap (unsigned long int number, unsigned long int address)
{
  assert (number == 29);
  ++calls;
  requested = address;
  if (address == 0)
    return (long int) kernel_break;
  if (failure != 0)
    return failure;
  kernel_break = address;
  return (long int) kernel_break;
}

int
main (void)
{
  errno = 1;
  assert (_dl_early_allocate (37) == (void *) XOS_HEAP_BEGIN);
  assert (calls == 2 && requested == XOS_HEAP_BEGIN + 37 && errno == 1);
  assert (__curbrk == (void *) (XOS_HEAP_BEGIN + 37));
  assert (_dl_early_allocate (SIZE_MAX) == NULL && calls == 3 && errno == 1);
  failure = -5;
  assert (_dl_early_allocate (1) == NULL && calls == 5 && errno == 1);
  assert (__curbrk == (void *) (XOS_HEAP_BEGIN + 37));

  assert (__brk (NULL) == 0 && requested == 0 && errno == 1);
  assert (__curbrk == (void *) (XOS_HEAP_BEGIN + 37));
  assert (__brk ((void *) XOS_HEAP_END) == -1 && errno == ENOMEM);
  failure = -12;
  assert (__brk ((void *) XOS_HEAP_BEGIN) == -1 && errno == EBUSY);
  failure = XOS_HEAP_BEGIN + 37;
  assert (__brk ((void *) XOS_HEAP_BEGIN) == -1 && errno == EIO);
  assert (__curbrk == (void *) (XOS_HEAP_BEGIN + 37));
  failure = 0;
  assert (__brk ((void *) XOS_HEAP_BEGIN) == 0);
  assert (__curbrk == (void *) XOS_HEAP_BEGIN);

  kernel_break = XOS_HEAP_END + 1;
  assert (_dl_early_allocate (16) == NULL);
  assert (__brk (NULL) == -1 && errno == EIO);
  assert (__curbrk == (void *) XOS_HEAP_BEGIN);
}
