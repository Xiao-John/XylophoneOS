/* SPDX-License-Identifier: Apache-2.0
   Expected: initial pthread_exit is joined, then final worker owns exit(0). */
#define _GNU_SOURCE 1
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static pthread_t initial;
static pthread_key_t key;
static int destructors, joined;

static void
destructor (void *value)
{
  if ((uintptr_t) value != 1 && (uintptr_t) value != 2)
    _Exit (2);
  __atomic_add_fetch (&destructors, 1, __ATOMIC_RELEASE);
}

static void
finish (void)
{
  if (!joined || __atomic_load_n (&destructors, __ATOMIC_ACQUIRE) != 2)
    _Exit (3);
  puts ("G3-T PASS initial pthread_exit join TSD and final-worker atexit");
}

static void *
worker (void *unused)
{
  (void) unused;
  if (pthread_setspecific (key, (void *) 2) != 0)
    _Exit (4);
  void *value = NULL;
  if (pthread_join (initial, &value) != 0
      || (uintptr_t) value != 0x1234567887654321ULL)
    _Exit (5);
  joined = 1;
  return NULL;
}

int
main (void)
{
  initial = pthread_self ();
  if (pthread_key_create (&key, destructor) != 0
      || pthread_setspecific (key, (void *) 1) != 0 || atexit (finish) != 0)
    return 6;
  pthread_t thread;
  if (pthread_create (&thread, NULL, worker, NULL) != 0)
    return 7;
  pthread_exit ((void *) (uintptr_t) 0x1234567887654321ULL);
}
