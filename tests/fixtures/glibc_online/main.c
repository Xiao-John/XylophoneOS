/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

typedef int (*value_fn) (void);
typedef int (*step_fn) (int);
typedef void (*bind_fn) (int *);
static int events[2], ready, release_worker, hold_started, hold_release;
static int explicit_exit, last_worker, lazy_tls;
static int started_workers, allow_touch;
static step_fn touch;
static __thread int main_tls = 7;

static void require (int good, const char *name)
{
  if (!good)
    {
      printf ("K3_FAIL %s errno=%d\n", name, errno);
      fflush (stdout);
      _Exit (90);
    }
}
static uint64_t now (void)
{
  struct timespec ts;
  require (clock_gettime (CLOCK_MONOTONIC, &ts) == 0, "monotonic clock");
  return (uint64_t) ts.tv_sec * 1000000000ULL + (uint64_t) ts.tv_nsec;
}
static void pause_one (void)
{
  const struct timespec ts = { 0, 1000000 };
  require (nanosleep (&ts, NULL) == 0, "short wait");
}
static void wait_flag_for (int *flag, int minimum, uint64_t budget)
{
  const uint64_t deadline = now () + budget;
  while (__atomic_load_n (flag, __ATOMIC_ACQUIRE) < minimum)
    {
      require (now () < deadline, "bounded synchronization");
      pause_one ();
    }
}
static void wait_flag (int *flag, int minimum)
{
  wait_flag_for (flag, minimum, 3000000000ULL);
}
static void *symbol (void *handle, const char *name)
{
  (void) dlerror ();
  void *result = dlsym (handle, name);
  require (result != NULL && dlerror () == NULL, name);
  return result;
}
static void *open_library (const char *name)
{
  (void) dlerror ();
  void *handle = dlopen (name, RTLD_NOW | RTLD_LOCAL);
  if (!handle) printf ("K3_DLOPEN_ERROR %s\n", dlerror ());
  require (handle != NULL, "approved library opens");
  return handle;
}
static void absent (const char *name)
{
  (void) dlerror ();
  void *handle = dlopen (name, RTLD_NOW | RTLD_NOLOAD);
  const char *error = dlerror ();
  require (handle == NULL && error == NULL, "mapping actually unloaded without loader error");
}
static void dependencies (void)
{
  absent ("libonline_isolated.so");
  void *first = open_library ("libonline_isolated.so");
  void *second = open_library ("libonline_isolated.so");
  require (first == second, "GNU repeated-open reference");
  value_fn value = (value_fn) symbol (second, "online_value");
  value_fn constructors = (value_fn) symbol (second, "online_constructors");
  step_fn step = (step_fn) symbol (second, "online_step");
  require (value () == 101 && constructors () == 1 && step (1) == 102, "dependency constructor once");
  require (dlclose (first) == 0 && value () == 102, "one reference remains");
  void *dependency = dlopen ("libonline_dep.so", RTLD_NOW | RTLD_NOLOAD);
  require (dependency != NULL, "dependency remains mapped");
  value_fn dep_value = (value_fn) symbol (dependency, "online_dep_value");
  require (dlclose (second) == 0 && dep_value () == 103, "destructor precedes dependency unload");
  require (dlclose (dependency) == 0, "last dependency reference");
  absent ("libonline_isolated.so");
  absent ("libonline_dep.so");
}
static void namespaces (void)
{
  void *base = open_library ("libonline_isolated.so");
  void *private = dlmopen (LM_ID_NEWLM, "libonline_isolated.so", RTLD_NOW | RTLD_LOCAL);
  if (!private) printf ("K3_DLMOPEN_ERROR %s\n", dlerror ());
  require (private != NULL && private != base, "independent namespace");
  Lmid_t namespace_id = -1;
  require (dlinfo (private, RTLD_DI_LMID, &namespace_id) == 0 && namespace_id == 1, "bounded namespace identity");
  value_fn base_value = (value_fn) symbol (base, "online_value");
  value_fn private_value = (value_fn) symbol (private, "online_value");
  step_fn private_step = (step_fn) symbol (private, "online_step");
  require (base_value () == 101 && private_value () == 101 && private_step (9) == 110
           && base_value () == 101, "namespace state and dependency isolation");
  (void) dlerror ();
  require (dlmopen (LM_ID_NEWLM, "libonline_isolated.so", RTLD_NOW) == NULL
           && dlerror () != NULL, "second private namespace rejected");
  require (private_value () == 110 && base_value () == 101, "rejection preserves live mappings");
  require (dlmopen (namespace_id, "libonline_tls.so", RTLD_NOW) == NULL
           && dlerror () != NULL, "private TLS/libc closure denied");
  require (dlclose (private) == 0 && dlclose (base) == 0, "namespace references released");
  private = dlmopen (LM_ID_NEWLM, "libonline_isolated.so", RTLD_NOW);
  require (private != NULL && ((value_fn) symbol (private, "online_value")) () == 101,
           "private namespace reclaimed and reused");
  require (dlclose (private) == 0, "reused namespace close");
}
static void *tls_worker (void *argument)
{
  const int index = (int) (uintptr_t) argument;
  require (main_tls == 7, "worker initial native TLS");
  main_tls = 70 + index;
  errno = 120 + index;
  if (lazy_tls)
    {
      __atomic_add_fetch (&started_workers, 1, __ATOMIC_RELEASE);
      /* Both workers already own their initial DTV before the main thread
         opens the new TLS module. Allow the loader its full five seconds. */
      wait_flag_for (&allow_touch, 1, 6000000000ULL);
    }
  require (touch (index + 1) == 32 + index, "dynamic TLS initial value and isolation");
  __atomic_add_fetch (&ready, 1, __ATOMIC_RELEASE);
  wait_flag (&release_worker, 1);
  require (main_tls == 70 + index && errno == 120 + index, "TLS and errno remain independent");
  if (last_worker)
    {
      const struct timespec delay = { 0, 300000000 };
      require (nanosleep (&delay, NULL) == 0, "last-worker bounded wait");
    }
  if (explicit_exit) pthread_exit ((void *) (uintptr_t) (0x40 + index));
  return (void *) (uintptr_t) (0x40 + index);
}
static void last_worker_exit_check (int status, void *argument)
{
  /* This is invoked by exit(0), after the last worker's thread-local cleanup.
     Its current native TLS and expandable DTV must still be usable. The GNU
     process finalizer was registered before this callback, so this callback
     runs before the retained DSO's process destructor. */
  require (status == 0 && argument == events, "last process callback status and identity");
  require (main_tls == 70, "last process callback retains worker native TLS");
  require (events[0] == 1 && events[1] == 0,
           "last worker TLS destructor precedes process callbacks");
  require (touch != NULL && touch (0) == 32,
           "last process callback retains worker dynamic TLS");
  require (events[0] == 1 && events[1] == 0,
           "callback lookup does not replay TLS destructors or finalize DSO");
  puts ("K3_LAST_THREAD_COMPLETE");
  fflush (stdout);
}
static void tls_lifetimes (int count)
{
  memset (events, 0, sizeof events);
  ready = release_worker = started_workers = allow_touch = 0;
  pthread_t threads[2];
  errno = 77;
  if (lazy_tls)
    {
      for (int i = 0; i < count; ++i)
        require (pthread_create (&threads[i], NULL, tls_worker,
                                 (void *) (uintptr_t) i) == 0,
                 "pre-existing pthread creation");
      wait_flag (&started_workers, count);
    }
  void *library = open_library ("libonline_tls.so");
  ((bind_fn) symbol (library, "online_bind")) (events);
  require (((value_fn) symbol (library, "online_constructors")) () == 1, "TLS DSO constructor");
  touch = (step_fn) symbol (library, "online_touch");
  /* Successful dlopen/dlsym may change errno; isolate the thread check. */
  errno = 77;
  if (lazy_tls)
    __atomic_store_n (&allow_touch, 1, __ATOMIC_RELEASE);
  else
    for (int i = 0; i < count; ++i)
      require (pthread_create (&threads[i], NULL, tls_worker,
                               (void *) (uintptr_t) i) == 0,
               "real pthread creation");
  wait_flag (&ready, count);
  require (main_tls == 7 && errno == 77, "main TLS/errno untouched");
  require (dlclose (library) == 0 && events[1] == 0, "TLS destructors prevent premature unload");
  void *retained = dlopen ("libonline_tls.so", RTLD_NOW | RTLD_NOLOAD);
  require (retained != NULL && dlclose (retained) == 0, "TLS-held mapping observable");
  __atomic_store_n (&release_worker, 1, __ATOMIC_RELEASE);
  if (last_worker) pthread_exit (NULL);
  for (int i = 0; i < count; ++i)
    {
      void *result = NULL;
      require (pthread_join (threads[i], &result) == 0 && result == (void *) (uintptr_t) (0x40 + i),
               "join and DTV retirement");
    }
  require (events[0] == count && events[1] == 0, "all TLS destructors ran before DSO finalization");
  retained = dlopen ("libonline_tls.so", RTLD_NOW | RTLD_NOLOAD);
  require (retained != NULL && dlclose (retained) == 0 && events[1] == 1,
           "last reference collects the formerly TLS-held DSO");
  absent ("libonline_tls.so");
}
void online_constructor_hold (void)
{
  __atomic_store_n (&hold_started, 1, __ATOMIC_RELEASE);
  wait_flag (&hold_release, 1);
}
static void *load_worker (void *ignored)
{
  (void) ignored;
  return open_library ("libonline_block.so");
}
static void concurrent_load (void)
{
  pthread_t thread;
  hold_started = hold_release = 0;
  require (pthread_create (&thread, NULL, load_worker, NULL) == 0, "constructor caller thread");
  wait_flag (&hold_started, 1);
  const uint64_t started = now ();
  (void) dlerror ();
  require (dlopen ("libonline_dep.so", RTLD_NOW) == NULL && dlerror () != NULL
           && now () - started < 500000000ULL, "competing loader returns bounded busy");
  __atomic_store_n (&hold_release, 1, __ATOMIC_RELEASE);
  void *handle = NULL;
  require (pthread_join (thread, &handle) == 0 && handle != NULL, "constructor completes after busy caller");
  require (((value_fn) symbol (handle, "online_constructors")) () == 1 && dlclose (handle) == 0,
           "constructor and unload remain consistent");
  absent ("libonline_block.so");
}
static void rejection (void)
{
  const char *names[] = { "libunapproved.so", "/apps/p1online/libonline_tls.so", "../libonline_tls.so" };
  for (unsigned int i = 0; i < sizeof names / sizeof names[0]; ++i)
    {
      (void) dlerror ();
      require (dlopen (names[i], RTLD_NOW) == NULL && dlerror () != NULL, "unapproved/path object rejected");
    }
  const int modes[] = { RTLD_LAZY, RTLD_NOW | RTLD_GLOBAL, RTLD_NOW | RTLD_NODELETE, RTLD_NOW | RTLD_DEEPBIND };
  for (unsigned int i = 0; i < sizeof modes / sizeof modes[0]; ++i)
    {
      (void) dlerror ();
      require (dlopen ("libonline_dep.so", modes[i]) == NULL && dlerror () != NULL, "unqualified mode rejected");
    }
  require (dlmopen (2, "libonline_dep.so", RTLD_NOW) == NULL && dlerror () != NULL,
           "namespace out of range rejected");
  dependencies ();
}
static void pin_replacement (void)
{
  const char *path = "/apps/p1online/libonline_isolated.so";
  const char *backup = "/apps/p1online/libonline_saved.so";
  require (rename (path, backup) == 0, "rename approved path after pin handoff");
  const int fd = open (path, O_CREAT | O_EXCL | O_WRONLY, 0600);
  const char bad[] = "not an ELF and not the approved immutable pin";
  require (fd >= 0 && write (fd, bad, sizeof bad) == (ssize_t) sizeof bad && close (fd) == 0,
           "replace pathname with unrelated bytes");
  dependencies ();
  require (unlink (path) == 0 && rename (backup, path) == 0, "restore fixture path");
}
int main (int argc, char **argv)
{
  require (argc == 2, "one exact case");
  const char *name = argv[1];
  if (!strcmp (name, "fixed"))
    {
      (void) dlerror ();
      require (dlopen ("libonline_dep.so", RTLD_NOW) == NULL && dlerror () != NULL,
               "startup-only generation keeps online denial");
      require (dlmopen (LM_ID_NEWLM, "libonline_dep.so", RTLD_NOW) == NULL
               && dlerror () != NULL, "startup-only namespace denial");
    }
  else if (!strcmp (name, "dependencies")) dependencies ();
  else if (!strcmp (name, "namespaces")) namespaces ();
  else if (!strcmp (name, "tls")) tls_lifetimes (2);
  else if (!strcmp (name, "lazy_tls")) { lazy_tls = 1; tls_lifetimes (2); }
  else if (!strcmp (name, "pthread_exit")) { explicit_exit = 1; tls_lifetimes (2); }
  else if (!strcmp (name, "last_worker"))
    {
      explicit_exit = last_worker = 1;
      require (on_exit (last_worker_exit_check, events) == 0, "last process callback registration");
      tls_lifetimes (1);
    }
  else if (!strcmp (name, "concurrent")) concurrent_load ();
  else if (!strcmp (name, "pin_replacement")) pin_replacement ();
  else if (!strcmp (name, "rejections")) rejection ();
  else if (!strcmp (name, "cycles")) for (int i = 0; i < 12; ++i) { dependencies (); tls_lifetimes (1); }
  else require (0, "known case");
  printf ("K3_PASS %s\n", name);
  return 0;
}
