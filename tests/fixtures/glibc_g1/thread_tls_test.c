/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <tls.h>
#include <ldsodefs.h>
#include "xos_thread_tls.h"

size_t dl_tls_static_size, dl_tls_static_align;
static int allocate_calls, release_calls, fail_allocate;
static struct pthread *last;
static struct xos_thread_reservation kernel_reservation;
static int starts, aborts, expected_releases;
xos_i64 __xos_thread_test_call (xos_u64 n, xos_u64 a, xos_u64 b)
{
  if (n == 38) {
    *(struct xos_thread_reservation *) (uintptr_t) b = kernel_reservation;
    return 0;
  }
  if (n == 39) {
    struct xos_thread_start_request *req = (void *) (uintptr_t) a;
    assert (req->thread_pointer == (uintptr_t) last);
    ++starts;
    return -2;
  }
  assert (n == 40 && a == kernel_reservation.tid && release_calls == expected_releases);
  ++aborts;
  return 0;
}
void *_dl_allocate_tls (void *tcb)
{
  struct pthread *p = tcb;
  ++allocate_calls;
  assert (p->header.self == p && p->header.tcb == p);
  assert (p->header.multiple_threads == 1 && p->setxid_futex == -1);
  assert (p->specific[0] == p->specific_1stblock && p->specific[1] == NULL);
  assert (p->header.dtv == NULL);
  if (fail_allocate) return NULL;
  p->header.dtv = &allocate_calls;
  last = p;
  return tcb;
}
void _dl_deallocate_tls (void *tcb, bool free_tcb)
{
  assert (tcb == last && !free_tcb && last->header.dtv == &allocate_calls);
  ++release_calls;
}
struct setup_context { struct pthread *pd; };
static xos_i64 setup (const struct xos_thread_reservation *r,
                      struct xos_thread_start_parameters *p, void *raw)
{
  struct setup_context *context = raw;
  int result = __xos_thread_tls_initialize (r, &context->pd);
  if (result != 0) return result;
  p->entry = 42; p->argument = 43; p->stack = 0x1000;
  p->thread_pointer = (uintptr_t) context->pd;
  return 0;
}
static void rollback (void *raw)
{
  struct setup_context *context = raw;
  if (context->pd != NULL) {
    __xos_thread_tls_release (context->pd);
    context->pd = NULL;
  }
}
int main (void)
{
  _Alignas(64) unsigned char region[4096];
  memset (region, 0xa5, sizeof region);
  struct xos_thread_reservation r = {0};
  r.tls_begin = (uintptr_t) region;
  r.tls_end = r.tls_begin + sizeof region;
  dl_tls_static_size = 512 + sizeof (struct pthread);
  dl_tls_static_align = 64;
  struct pthread *out = (struct pthread *) (uintptr_t) 1;
  r.tls_end = r.tls_begin + 64;
  assert (__xos_thread_tls_initialize (&r, &out) == -1);
  assert (out == (struct pthread *) (uintptr_t) 1 && allocate_calls == 0);
  r.tls_end = r.tls_begin + sizeof region;
  fail_allocate = 1;
  assert (__xos_thread_tls_initialize (&r, &out) == -2);
  assert (out == (struct pthread *) (uintptr_t) 1 && allocate_calls == 1 && release_calls == 0);
  fail_allocate = 0;
  assert (__xos_thread_tls_initialize (&r, &out) == 0);
  assert (out == last && allocate_calls == 2 && (uintptr_t) out % 64 == 0);
  __xos_thread_tls_release (out);
  assert (release_calls == 1);
  kernel_reservation = r;
  kernel_reservation.tid = 42;
  struct setup_context context = {0};
  struct xos_thread_launch_result result;
  expected_releases = 2;
  assert (__xos_thread_launch (65536, 4096, 0, setup, rollback, &context, &result) == -2);
  assert (release_calls == 2 && starts == 1 && aborts == 1 && context.pd == NULL && result.tid == 0);
  fail_allocate = 1;
  assert (__xos_thread_launch (65536, 4096, 0, setup, rollback, &context, &result) == -2);
  assert (release_calls == 2 && starts == 1 && aborts == 2 && context.pd == NULL && result.tid == 0);
}
