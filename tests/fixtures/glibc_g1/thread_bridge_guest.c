/* SPDX-License-Identifier: Apache-2.0
   Standalone XOS guest test of the private native bridge.  No libc is linked. */
#include "xos_thread_create.h"

static xos_u64 child_result;
static int rollback_count;
static struct xos_thread_launch_result launch;
static int invalid_start;
static xos_i64 trap (xos_u64 n, xos_u64 a, xos_u64 b)
{
  xos_i64 result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (n), "D" (a), "S" (b), "d" (0L) : "memory", "cc");
  return result;
}
static void finish (xos_u64 code) __attribute__ ((noreturn));
static void finish (xos_u64 code)
{
  (void) trap (2, code, 0);
  __builtin_trap ();
}
void guest_thread_enter (void *);
void guest_thread_worker (void *raw) __attribute__ ((noreturn, used));
void guest_thread_worker (void *raw)
{
  xos_u64 tp;
  __asm__ volatile ("mov %%fs:0,%0" : "=r" (tp));
  if (raw != &child_result || tp == 0 || *(xos_u64 *) tp != tp)
    finish (90);
  child_result = 0xabc;
  if (trap (42, 0, 0) != 0)
    finish (91);
  (void) trap (43, 0x1234, 0);
  finish (92);
}
__asm__ (".text\n.globl guest_thread_enter\n"
         "guest_thread_enter:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\n"
         "call guest_thread_worker\nud2\n");
static xos_i64 setup (const struct xos_thread_reservation *r,
                      struct xos_thread_start_parameters *p, void *context)
{
  if (context != &launch || __atomic_load_n (&launch.tid, __ATOMIC_ACQUIRE) != r->tid)
    return -77;
  *(xos_u64 *) r->tls_begin = r->tls_begin;
  p->entry = invalid_start ? 0 : (xos_u64) guest_thread_enter;
  p->argument = (xos_u64) &child_result;
  p->stack = r->stack_top;
  p->thread_pointer = r->tls_begin;
  return 0;
}
static void rollback (void *context)
{
  if (context == &launch)
    ++rollback_count;
}
int guest_main (void) __attribute__ ((used));
int guest_main (void)
{
  struct xos_thread_header header = {1, sizeof (header), 0};
  if (trap (52, (xos_u64) &header, 0) != 0) return 10;
  invalid_start = 1;
  if (__xos_thread_launch (65536, 4096, 0, setup, rollback, &launch, &launch) == 0) return 11;
  if (launch.abort_error != 0 || launch.tid != 0 || launch.started || rollback_count != 1) return 12;
  invalid_start = 0;
  if (__xos_thread_launch (65536, 4096, 0, setup, rollback, &launch, &launch) != 0) return 13;
  if (!launch.started || !launch.tid || launch.abort_error != 0 || rollback_count != 1) return 14;
  xos_u64 value = 0;
  if (trap (44, launch.tid, (xos_u64) &value) != 0) return 15;
  if (value != 0x1234 || child_result != 0xabc) return 16;
  return 0;
}
__asm__ (".section .text.entry,\"ax\"\n.globl _start\n"
         "_start:\ncld\nxor %ebp,%ebp\nand $-16,%rsp\n"
         "call guest_main\nmov %eax,%edi\nmov $2,%eax\nint $0x80\nud2\n");
