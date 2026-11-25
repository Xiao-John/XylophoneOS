/* SPDX-License-Identifier: Apache-2.0
   Normal process exit while peers own locks, allocate, and wait on a condvar. */
#define _GNU_SOURCE 1
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void
check_failed (unsigned line)
{
  char digits[16];
  unsigned count = 0;
  do { digits[count++] = '0' + line % 10; line /= 10; } while (line);
  const char message[] = "G3-X active exit assertion failed line=";
  (void) write (2, message, sizeof (message) - 1);
  while (count)
    (void) write (2, &digits[--count], 1);
  (void) write (2, "\n", 1);
  _exit (95);
}
#define CHECK(value) do { if (!(value)) check_failed (__LINE__); } while (0)

static pthread_mutex_t held_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t idle_mutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t idle_cond = PTHREAD_COND_INITIALIZER;
static pthread_key_t key;
static pthread_t locker;
static atomic_int held, release_worker, idle_ready, tsd_cleaned;
static atomic_uint tls_cleaned;
static atomic_uint allocations;
static int phase;
static __thread unsigned tls_cookie;
extern void *__dso_handle;
extern int __cxa_thread_atexit_impl (void (*) (void *), void *, void *);
static FILE *output_file;
static char stdout_buffer[2048], file_buffer[2048];
static const char file_path[] = "/g3_exit_flush.txt";
static const char file_text[] = "main buffered\ncallback buffered\nfini buffered\n";

/* Exercise the actual C++ TLS destructor ABI without importing a newlib
   libstdc++. Full C++ library qualification remains a separate SDK module. */
static void
tls_cleanup (void *argument)
{
  CHECK (argument == &tls_cookie);
  if (tls_cookie == 0x31)
    {
      CHECK (phase == 0);
      atomic_fetch_or_explicit (&tls_cleaned, 1, memory_order_release);
    }
  else
    {
      CHECK (tls_cookie == 0x42 && phase == 1);
      atomic_fetch_or_explicit (&tls_cleaned, 2, memory_order_release);
    }
  tls_cookie = 0;
}

static void
tsd_cleanup (void *value)
{
  CHECK (value == (void *) (uintptr_t) 0x4219);
  CHECK ((atomic_load_explicit (&tls_cleaned, memory_order_acquire) & 2) != 0);
  atomic_store_explicit (&tsd_cleaned, 1, memory_order_release);
}

static void *
hold_then_release (void *ignored)
{
  (void) ignored;
  tls_cookie = 0x42;
  CHECK (__cxa_thread_atexit_impl (tls_cleanup, &tls_cookie, &__dso_handle) == 0);
  CHECK (pthread_setspecific (key, (void *) (uintptr_t) 0x4219) == 0);
  CHECK (pthread_mutex_lock (&held_mutex) == 0);
  flockfile (stdout);
  atomic_store_explicit (&held, 1, memory_order_release);
  while (!atomic_load_explicit (&release_worker, memory_order_acquire))
    sched_yield ();
  struct timespec deadline;
  CHECK (clock_gettime (CLOCK_MONOTONIC, &deadline) == 0);
  deadline.tv_nsec += 200000000;
  if (deadline.tv_nsec >= 1000000000)
    { ++deadline.tv_sec; deadline.tv_nsec -= 1000000000; }
  pthread_mutex_t delay_mutex = PTHREAD_MUTEX_INITIALIZER;
  pthread_cond_t delay_cond = PTHREAD_COND_INITIALIZER;
  CHECK (pthread_mutex_lock (&delay_mutex) == 0);
  int waited;
  do
    waited = pthread_cond_clockwait (&delay_cond, &delay_mutex,
                                     CLOCK_MONOTONIC, &deadline);
  while (waited == 0);
  CHECK (waited == ETIMEDOUT);
  CHECK (pthread_mutex_unlock (&delay_mutex) == 0);
  CHECK (pthread_cond_destroy (&delay_cond) == 0);
  CHECK (pthread_mutex_destroy (&delay_mutex) == 0);
  CHECK (fputs ("G3-X worker buffered\n", stdout) >= 0);
  funlockfile (stdout);
  CHECK (pthread_mutex_unlock (&held_mutex) == 0);
  return (void *) (uintptr_t) UINT64_C (0x12345678abcdef09);
}

static void *
wait_for_process_exit (void *ignored)
{
  (void) ignored;
  CHECK (pthread_mutex_lock (&idle_mutex) == 0);
  atomic_store_explicit (&idle_ready, 1, memory_order_release);
  for (;;)
    CHECK (pthread_cond_wait (&idle_cond, &idle_mutex) == 0);
}

static void *
allocate_until_process_exit (void *ignored)
{
  (void) ignored;
  for (;;)
    {
      char *memory = malloc (257);
      CHECK (memory != NULL);
      memset (memory, 0x5c, 257);
      CHECK (memory[256] == 0x5c);
      free (memory);
      atomic_fetch_add_explicit (&allocations, 1, memory_order_release);
    }
}

static void
second_callback (void)
{
  CHECK (phase == 0);
  CHECK (atomic_load_explicit (&tls_cleaned, memory_order_acquire) == 1);
  phase = 1;
  atomic_store_explicit (&release_worker, 1, memory_order_release);
  /* This waits for a live peer, which in turn must retain stdio/TLS/VM. */
  CHECK (pthread_mutex_lock (&held_mutex) == 0);
  CHECK (pthread_mutex_unlock (&held_mutex) == 0);
  void *result = NULL;
  CHECK (pthread_join (locker, &result) == 0);
  CHECK ((uintptr_t) result == UINT64_C (0x12345678abcdef09));
  CHECK (atomic_load_explicit (&tsd_cleaned, memory_order_acquire) == 1);
  CHECK (atomic_load_explicit (&tls_cleaned, memory_order_acquire) == 3);
  unsigned before = atomic_load_explicit (&allocations, memory_order_acquire);
  while (atomic_load_explicit (&allocations, memory_order_acquire) == before)
    sched_yield ();
  void *memory = malloc (131071);
  CHECK (memory != NULL);
  memset (memory, 0x6b, 131071);
  free (memory);
  CHECK (fputs ("G3-X callback second\n", stdout) >= 0);
}

static void
first_callback (void)
{
  CHECK (phase == 1);
  phase = 2;
  pthread_t unchanged = (pthread_t) 0xabcdef;
  CHECK (pthread_create (&unchanged, NULL, wait_for_process_exit, NULL) == EBUSY);
  CHECK (unchanged == (pthread_t) 0xabcdef);
  CHECK (fputs ("callback buffered\n", output_file) >= 0);
  CHECK (fputs ("G3-X callback first\n", stdout) >= 0);
}

static void __attribute__ ((destructor))
final_callback (void)
{
  if (output_file == NULL)
    return;
  CHECK (phase == 2);
  phase = 3;
  CHECK (fputs ("fini buffered\n", output_file) >= 0);
  CHECK (fputs ("G3-X fini and complete stdout flush\n", stdout) >= 0);
}

int
main (int argc, char **argv)
{
  if (argc == 2 && strcmp (argv[1], "verify") == 0)
    {
      FILE *input = fopen (file_path, "rb");
      char bytes[sizeof (file_text) + 16];
      CHECK (input != NULL);
      size_t length = fread (bytes, 1, sizeof (bytes), input);
      CHECK (length == sizeof (file_text) - 1);
      CHECK (memcmp (bytes, file_text, length) == 0 && !ferror (input));
      CHECK (fclose (input) == 0 && unlink (file_path) == 0);
      puts ("G3-X PASS process-exit file flush bytes and resource release");
      return 0;
    }
  CHECK (argc == 1 || (argc == 2 && strcmp (argv[1], "exit") == 0));
  CHECK (setvbuf (stdout, stdout_buffer, _IOFBF, sizeof (stdout_buffer)) == 0);
  puts ("G3-X BEGIN active peers and buffered files");
  CHECK (fflush (stdout) == 0);
  output_file = fopen (file_path, "w");
  CHECK (output_file != NULL);
  CHECK (setvbuf (output_file, file_buffer, _IOFBF, sizeof (file_buffer)) == 0);
  CHECK (fputs ("main buffered\n", output_file) >= 0);
  CHECK (pthread_key_create (&key, tsd_cleanup) == 0);
  tls_cookie = 0x31;
  CHECK (__cxa_thread_atexit_impl (tls_cleanup, &tls_cookie, &__dso_handle) == 0);
  CHECK (atexit (first_callback) == 0 && atexit (second_callback) == 0);
  pthread_t waiter, allocator;
  CHECK (pthread_create (&locker, NULL, hold_then_release, NULL) == 0);
  CHECK (pthread_create (&waiter, NULL, wait_for_process_exit, NULL) == 0);
  CHECK (pthread_create (&allocator, NULL, allocate_until_process_exit, NULL) == 0);
  while (!atomic_load_explicit (&held, memory_order_acquire)
         || !atomic_load_explicit (&idle_ready, memory_order_acquire)
         || atomic_load_explicit (&allocations, memory_order_acquire) == 0)
    sched_yield ();
  if (argc == 2)
    exit (39);
  return 37;
}
