/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_thread_create.h"

#if !defined XOS_GLIBC_THREAD_TEST && (!defined __x86_64__ || defined __ILP32__)
# error "XOS thread bridge supports x86-64 LP64 only"
#endif
_Static_assert (sizeof (struct xos_thread_prepare_request) == 40, "prepare ABI");
_Static_assert (sizeof (struct xos_thread_reservation) == 56, "reservation ABI");
_Static_assert (sizeof (struct xos_thread_start_request) == 56, "start ABI");

#ifdef XOS_GLIBC_THREAD_TEST
extern xos_i64 __xos_thread_test_call (xos_u64, xos_u64, xos_u64);
# define xos_trap __xos_thread_test_call
#else
static inline xos_i64
xos_trap (xos_u64 number, xos_u64 first, xos_u64 second)
{
  xos_i64 result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (0L)
                    : "memory", "cc");
  return result;
}
#endif

xos_i64
__xos_thread_prepare (xos_u64 stack, xos_u64 tls, xos_u64 flags,
                      struct xos_thread_reservation *reservation)
{
  struct xos_thread_prepare_request request = {
    .header = { 1, sizeof (request), 0 },
    .stack_bytes = stack, .tls_bytes = tls, .flags = flags
  };
  return xos_trap (38, (xos_u64) &request, (xos_u64) reservation);
}

xos_i64
__xos_thread_start (xos_u64 tid, xos_u64 entry, xos_u64 argument,
                    xos_u64 stack, xos_u64 thread_pointer)
{
  struct xos_thread_start_request request = {
    .header = { 1, sizeof (request), 0 },
    .tid = tid, .entry = entry, .argument = argument, .stack = stack,
    .thread_pointer = thread_pointer
  };
  return xos_trap (39, (xos_u64) &request, 0);
}

xos_i64
__xos_thread_abort (xos_u64 tid)
{
  return xos_trap (40, tid, 0);
}

xos_i64
__xos_thread_launch (xos_u64 stack, xos_u64 tls, xos_u64 flags,
                     xos_thread_setup_fn setup, void *context,
                     struct xos_thread_launch_result *result)
{
  struct xos_thread_reservation reservation = { 0 };
  struct xos_thread_start_parameters parameters = { 0 };
  xos_i64 error;

  /* The caller owns RESULT until this function returns.  The published ID
     is tentative until success; on failed rollback it identifies the
     reservation whose final state must be resolved by the caller.  */
  __atomic_store_n (&result->tid, 0, __ATOMIC_RELEASE);
  result->abort_error = 0;
  result->started = 0;
  error = __xos_thread_prepare (stack, tls, flags, &reservation);
  if (error != 0)
    return error;
  __atomic_store_n (&result->tid, reservation.tid, __ATOMIC_RELEASE);
  error = setup (&reservation, &parameters, context);
  if (error == 0)
    error = __xos_thread_start (reservation.tid, parameters.entry,
                                parameters.argument, parameters.stack,
                                parameters.thread_pointer);
  if (error == 0)
    {
      result->started = 1;
      return 0;
    }
  result->abort_error = __xos_thread_abort (reservation.tid);
  if (result->abort_error == 0)
    __atomic_store_n (&result->tid, 0, __ATOMIC_RELEASE);
  return error;
}

/* glibc x86-64 TLS_TCB_AT_TP: dl_tls_static_size includes the TCB,
   and the remaining static TLS is placed immediately before the TCB.  */
int
__xos_thread_tls_layout (const struct xos_thread_reservation *reservation,
                         xos_u64 static_size, xos_u64 alignment,
                         xos_u64 descriptor_size,
                         struct xos_thread_tls_layout *layout)
{
  const xos_u64 max = (xos_u64) -1;
  xos_u64 prefix, minimum, pointer;
  if (alignment < 16 || (alignment & (alignment - 1)) != 0
      || descriptor_size < 16 || static_size < descriptor_size
      || reservation->tls_begin >= reservation->tls_end)
    return -1;
  prefix = static_size - descriptor_size;
  if (prefix > max - reservation->tls_begin)
    return -1;
  minimum = reservation->tls_begin + prefix;
  if (minimum > max - (alignment - 1))
    return -1;
  pointer = (minimum + alignment - 1) & ~(alignment - 1);
  if (pointer > reservation->tls_end
      || descriptor_size > reservation->tls_end - pointer)
    return -1;
  struct xos_thread_tls_layout value = { pointer - prefix, pointer,
                                         pointer + descriptor_size };
  *layout = value;
  return 0;
}
