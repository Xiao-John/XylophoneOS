/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <ldsodefs.h>
#include <pthreadP.h>
#include <shlib-compat.h>
#include <version.h>

extern td_thr_events_t __nptl_threads_events;
libc_hidden_proto (__nptl_threads_events)
td_thr_events_t __nptl_threads_events;
libc_hidden_data_def (__nptl_threads_events)

extern struct pthread *__nptl_last_event;
libc_hidden_proto (__nptl_last_event)
struct pthread *__nptl_last_event;
libc_hidden_data_def (__nptl_last_event)

const char __nptl_version[] = VERSION;
#ifdef SHARED
struct rtld_global *__nptl_rtld_global = &_rtld_global;
#else
# include <atomic.h>
# include <ctype.h>
# include <libc-diag.h>
# include <libc-internal.h>
# include <libioP.h>
# include <resolv.h>
# include <stdlib.h>
# include <sys/single_threaded.h>
# include "xos_static_worker.h"
# include "xos_thread_identity.h"

struct worker_input
{
  void *(*start) (void *);
  void *argument;
  bool c11;
};

static xos_i64
prepare_worker (struct pthread *pd,
                const struct xos_thread_reservation *reservation,
                void **argument)
{
  const struct worker_input *input = *argument;
  if (reservation->tid == 0 || reservation->tid > FUTEX_TID_MASK)
    return -5;
  pd->tid = reservation->tid;
  pd->stackblock = (void *) reservation->stack_bottom;
  pd->stackblock_size = reservation->stack_top - reservation->stack_bottom;
  pd->start_routine = input->start;
  pd->arg = input->argument;
  pd->c11 = input->c11;
  *argument = pd;
  return 0;
}

static void *
start_worker (void *argument)
{
  struct pthread *pd = argument;
  __resp = &pd->res;
  __ctype_init ();

  struct pthread_unwind_buf unwind;
  DIAG_PUSH_NEEDS_COMMENT;
  /* _setjmp writes the common prefix, without saving the signal mask. */
  DIAG_IGNORE_NEEDS_COMMENT (11, "-Wstringop-overflow");
  int exiting = _setjmp ((struct __jmp_buf_tag *) unwind.cancel_jmp_buf);
  DIAG_POP_NEEDS_COMMENT;
  unwind.priv.data.prev = NULL;
  unwind.priv.data.cleanup = NULL;
  if (!exiting)
    {
      pd->cleanup_jmp_buf = &unwind;
      if (pd->c11)
        {
          int (*start) (void *) = (int (*) (void *)) pd->start_routine;
          pd->result = (void *) (intptr_t) start (pd->arg);
        }
      else
        pd->result = pd->start_routine (pd->arg);
    }
  pd->cleanup_jmp_buf = NULL;
  return pd->result;
}

static void
cleanup_worker (void)
{
  call_function_static_weak (__call_tls_dtors);
  __nptl_deallocate_tsd ();
  __libc_thread_freeres ();
  atomic_fetch_add_relaxed (&__nptl_nthreads, -1);
}

static void
last_worker_exit (void)
{
  exit (0);
}

static int
create_worker (pthread_t *thread, const struct pthread_attr *attr,
               struct worker_input *input)
{
  /* XOS reserves the stack and an unmapped gap on its own. Support
     inherited scheduling and kernel-provided stacks up to 2 MiB. */
  if ((attr->flags & (ATTR_FLAG_STACKADDR | ATTR_FLAG_NOTINHERITSCHED
                       | ATTR_FLAG_SCOPEPROCESS | ATTR_FLAG_DO_RSEQ)) != 0
      || (attr->extension != NULL
          && (attr->extension->cpuset != NULL || attr->extension->sigmask_set))
      || attr->guardsize > 0xe0000)
    return ENOTSUP;
  size_t stacksize;
  int stack_error = __pthread_attr_getstacksize ((const pthread_attr_t *) attr,
                                                 &stacksize);
  if (stack_error != 0)
    return stack_error;
  if (stacksize == 0)
    stacksize = 256 * 1024;
  if (stacksize < 64 * 1024 || stacksize > 2 * 1024 * 1024)
    return EINVAL;
  stacksize = (stacksize + 4095) & -4096UL;

  struct xos_thread_header profile = { 1, sizeof (profile), 0 };
  xos_i64 status = xos_thread_lifecycle (52, (xos_u64) &profile, 0);
  if (status != 0)
    return status == -18 ? ENOTSUP : xos_thread_lifecycle_error (status);

  /* Initialize stdio locking before any new worker can execute. The
     worker's cleanup decrements the count after it finishes using libc. */
  if (__libc_single_threaded_internal)
    {
      _IO_enable_locks ();
      THREAD_SETMEM (THREAD_SELF, header.multiple_threads, 1);
      __libc_single_threaded_internal = 0;
      __libc_single_threaded = 0;
    }
  atomic_fetch_add_relaxed (&__nptl_nthreads, 1);
  struct xos_static_worker worker = {
    .run = start_worker, .argument = input, .cleanup = cleanup_worker,
    .last_process_exit = last_worker_exit, .prepare = prepare_worker
  };
  struct xos_thread_launch_result launch;
  status = __xos_static_worker_launch (stacksize,
            (attr->flags & ATTR_FLAG_DETACHSTATE) != 0, &worker, &launch);
  if (status == 0)
    {
      *thread = (pthread_t) launch.tid;
      return 0;
    }

  atomic_fetch_add_relaxed (&__nptl_nthreads, -1);
  if (launch.abort_error != 0)
    __libc_fatal ("XOS glibc: could not release a thread reservation\n");
  if (status == -5 || status == -17)
    return EAGAIN;
  if (status == -18)
    return ENOTSUP;
  return xos_thread_lifecycle_error (status);
}
#endif

int
__pthread_create_2_1 (pthread_t *thread, const pthread_attr_t *attr,
                      void *(*start) (void *), void *argument)
{
#ifdef SHARED
  /* Shared builds require an independent dynamic-TLS lifetime policy. */
  (void) thread;
  (void) attr;
  (void) start;
  (void) argument;
  return ENOTSUP;
#else
  struct worker_input input = { start, argument, attr == ATTR_C11_THREAD };
  if (attr != NULL && !input.c11)
    return create_worker (thread, (const struct pthread_attr *) attr, &input);

  union pthread_attr_transparent defaults;
  int result = __pthread_getattr_default_np (&defaults.external);
  if (result != 0)
    return result;
  result = create_worker (thread, &defaults.internal, &input);
  __pthread_attr_destroy (&defaults.external);
  return result;
#endif
}
versioned_symbol (libc, __pthread_create_2_1, pthread_create, GLIBC_2_34);
libc_hidden_ver (__pthread_create_2_1, __pthread_create)
#ifndef SHARED
strong_alias (__pthread_create_2_1, __pthread_create)
#endif

/* XOS has no debugger register layout compatible with Linux proc_service. */
#undef DB_THREAD_SELF
#include <nptl_db/db_info.c>
