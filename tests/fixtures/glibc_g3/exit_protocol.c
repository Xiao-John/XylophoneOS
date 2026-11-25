/* SPDX-License-Identifier: Apache-2.0
   Public exit concurrency plus native cleanup ownership/deadline rejection. */
#define _GNU_SOURCE 1
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct cleanup_request
{
  uint32_t version, size;
  uint64_t header_reserved, deadline_ns;
  int32_t timeout_status;
  uint32_t reserved;
};
_Static_assert (sizeof (struct cleanup_request) == 32, "cleanup request ABI");
struct native_header { uint32_t version, size; uint64_t reserved; };
struct native_prepare { struct native_header header; uint64_t stack, tls, flags; };
struct native_reservation { struct native_header header; uint64_t tid, bottom, top, tls_begin, tls_end; };
struct native_start { struct native_header header; uint64_t tid, entry, argument, stack, tp; };
_Static_assert (sizeof (struct native_prepare) == 40, "thread prepare ABI");
_Static_assert (sizeof (struct native_reservation) == 56, "thread reservation ABI");
_Static_assert (sizeof (struct native_start) == 56, "thread start ABI");

static long
native (unsigned long number, unsigned long first, unsigned long second,
        unsigned long third)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (third)
                    : "memory", "cc");
  return result;
}

#define CHECK(value) do { if (!(value)) { \
  const char message[] = "G3-X exit protocol assertion failed\n"; \
  (void) write (2, message, sizeof (message) - 1); _exit (94); } } while (0)

static atomic_int go, entered, peer_checked;
static const char *mode;
static int callback_count;
static char buffer[512];

static struct cleanup_request
request_after (uint64_t duration, int status)
{
  long now = native (46, 0, 0, 0);
  CHECK (now >= 0);
  struct cleanup_request request = { 1, sizeof (request), 0,
    (uint64_t) now + duration, status, 0 };
  return request;
}

static long
claim (struct cleanup_request *request)
{
  return native (51, 1, (uintptr_t) request, 0);
}

static void *
peer (void *ignored)
{
  (void) ignored;
  while (!atomic_load_explicit (&go, memory_order_acquire))
    sched_yield ();
  if (strcmp (mode, "abi") == 0)
    {
      struct cleanup_request request = request_after (1000000000, 91);
      CHECK (claim (&request) == -12);
      CHECK (native (51, 0, 0, 0) == -6);
      atomic_store_explicit (&peer_checked, 1, memory_order_release);
      return (void *) (uintptr_t) UINT64_C (0xaabbccddee112233);
    }
  atomic_store_explicit (&entered, 1, memory_order_release);
  if (strcmp (mode, "worker") == 0)
    exit (41);
  exit (91);
}

static void
last_callback (void)
{
  CHECK (++callback_count == 2);
  puts ("G3-X callback last once");
}

static void
first_callback (void)
{
  CHECK (++callback_count == 1);
  puts ("G3-X callback first once");
  if (strcmp (mode, "recursive") == 0)
    exit (43);
  if (strcmp (mode, "concurrent") == 0)
    {
      atomic_store_explicit (&go, 1, memory_order_release);
      while (!atomic_load_explicit (&entered, memory_order_acquire))
        sched_yield ();
      long now = native (46, 0, 0, 0);
      CHECK (now >= 0 && native (47, (unsigned long) now + 100000000, 0, 0) == 0);
      puts ("G3-X concurrent caller preserved owner status");
    }
}

static void
quick_last_callback (void)
{
  const char message[] = "G3-X quick callback last\n";
  CHECK (++callback_count == 2);
  CHECK (write (2, message, sizeof (message) - 1) == sizeof (message) - 1);
}

static void
quick_first_callback (void)
{
  const char message[] = "G3-X quick callback first\n";
  CHECK (++callback_count == 1);
  CHECK (write (2, message, sizeof (message) - 1) == sizeof (message) - 1);
}

static void
abi_rejections (void)
{
  struct cleanup_request good = request_after (1000000000, 125), bad;
  CHECK (native (51, 2, 0, 0) == -2);
  CHECK (native (51, 0, (uintptr_t) &good, 0) == -2);
  CHECK (native (51, 0, 0, 1) == -2);
  CHECK (native (51, 1, 0, 0) == -11);
  CHECK (native (51, 1, UINT64_C (0xfffffffffffffff0), 0) == -11);
  bad = good; bad.version = 2; CHECK (claim (&bad) == -2);
  bad = good; bad.size = 24; CHECK (claim (&bad) == -2);
  bad = good; bad.header_reserved = 1; CHECK (claim (&bad) == -2);
  bad = good; bad.reserved = 1; CHECK (claim (&bad) == -2);
  bad = good; bad.timeout_status = 0; CHECK (claim (&bad) == -2);
  bad = good; bad.deadline_ns = 0; CHECK (claim (&bad) == -2);
  bad = good; bad.deadline_ns = (uint64_t) native (46, 0, 0, 0); CHECK (claim (&bad) == -2);
  bad = good; bad.deadline_ns = UINT64_MAX; CHECK (claim (&bad) == -2);
  bad = request_after (31000000000UL, 125); CHECK (claim (&bad) == -2);
  /* All rejected requests must leave thread creation and exit ownership intact. */
  pthread_t worker;
  CHECK (pthread_create (&worker, NULL, peer, NULL) == 0);
  struct native_prepare prepare = { { 1, sizeof (prepare), 0 }, 65536, 16, 0 };
  struct native_reservation reserved;
  CHECK (native (38, (uintptr_t) &prepare, (uintptr_t) &reserved, 0) == 0);
  good = request_after (1000000000, 125);
  CHECK (claim (&good) == 0);
  struct cleanup_request again = request_after (30000000000UL, 124);
  CHECK (claim (&again) == 0);
  struct native_reservation unchanged_reservation;
  memset (&unchanged_reservation, 0x5a, sizeof (unchanged_reservation));
  struct native_reservation before = unchanged_reservation;
  CHECK (native (38, (uintptr_t) &prepare, (uintptr_t) &unchanged_reservation, 0) == -6);
  CHECK (memcmp (&unchanged_reservation, &before, sizeof (before)) == 0);
  struct native_start start = { { 1, sizeof (start), 0 }, reserved.tid, 0, 0,
    reserved.top, reserved.tls_begin };
  CHECK (native (39, (uintptr_t) &start, 0, 0) == -6);
  CHECK (native (40, reserved.tid, 0, 0) == 0);
  pthread_t unchanged = (pthread_t) 0x1234;
  CHECK (pthread_create (&unchanged, NULL, peer, NULL) == EBUSY);
  CHECK (unchanged == (pthread_t) 0x1234);
  atomic_store_explicit (&go, 1, memory_order_release);
  void *result = NULL;
  CHECK (pthread_join (worker, &result) == 0);
  CHECK ((uintptr_t) result == UINT64_C (0xaabbccddee112233));
  CHECK (atomic_load_explicit (&peer_checked, memory_order_acquire) == 1);
  puts ("G3-X PASS ABI rejection ownership peer cleanup and fixed deadline");
  CHECK (fflush (stdout) == 0);
  /* No yield or blocking call: the kernel timer must terminate this owner at
     the original one-second deadline with 125, not the repeat request's 124. */
  for (;;)
    __asm__ volatile ("pause" : : : "memory");
}

int
main (int argc, char **argv)
{
  CHECK (argc == 2);
  mode = argv[1];
  if (strcmp (mode, "abi") == 0)
    abi_rejections ();
  if (strcmp (mode, "fault") == 0 || strcmp (mode, "abandon") == 0)
    {
      pthread_t waiter;
      CHECK (pthread_create (&waiter, NULL, peer, NULL) == 0);
      struct cleanup_request request = request_after (1000000000, 127);
      CHECK (claim (&request) == 0);
      printf ("G3-X owner %s ready\n", mode);
      CHECK (fflush (stdout) == 0);
      if (strcmp (mode, "fault") == 0)
        __asm__ volatile ("ud2");
      pthread_exit (NULL);
    }
  CHECK (strcmp (mode, "recursive") == 0 || strcmp (mode, "worker") == 0
         || strcmp (mode, "concurrent") == 0 || strcmp (mode, "quick") == 0);
  CHECK (setvbuf (stdout, buffer, _IOFBF, sizeof (buffer)) == 0);
  puts ("G3-X public process exit begin");
  CHECK (fflush (stdout) == 0);
  CHECK (atexit (last_callback) == 0 && atexit (first_callback) == 0);
  if (strcmp (mode, "recursive") == 0)
    exit (37);
  pthread_t worker;
  CHECK (pthread_create (&worker, NULL, peer, NULL) == 0);
  if (strcmp (mode, "quick") == 0)
    {
      CHECK (at_quick_exit (quick_last_callback) == 0
             && at_quick_exit (quick_first_callback) == 0);
      CHECK (fputs ("G3-X quick pending stdout\n", stdout) >= 0);
      quick_exit (45);
    }
  if (strcmp (mode, "concurrent") == 0)
    exit (37);
  atomic_store_explicit (&go, 1, memory_order_release);
  for (;;)
    __asm__ volatile ("pause" : : : "memory");
}
