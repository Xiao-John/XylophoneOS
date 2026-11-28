/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "xos_rtld_mapping.h"

static xos_u64 clock_value = 1000, process = 17;
static _Thread_local xos_u64 thread = 1;
static int startup_closes;
#ifdef XOS_ONLINE_CLOSURE
static int requests, sends, fail_transport, poisoned, oversized, stale;
#endif
static struct xos_rtld_images images;
long __xos_file_test_trap (xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
  assert (!second && !third);
  if (number == 6) return process;
  if (number == 46) return clock_value;
  if (number == 22) { ((xos_u32 *) first)[0] = 68; ((xos_u32 *) first)[1] = 69; return 0; }
  if (number == 41)
    {
      struct { xos_u32 version, size; xos_u64 reserved, pid, tid, bottom, top, tp; } info
        = { 1, 56, 0, process, thread, 0x1000, 0x2000, 0x3000 };
      _Static_assert (sizeof info == 56, "real native output extent");
      memcpy ((void *) first, &info, sizeof info);
      return 0;
    }
  assert (!"unexpected native operation"); return -1;
}
long __xos_file_session_call_until (struct xos_file_session *session,
                                    struct xos_file_request *request,
                                    struct xos_file_response *response, xos_u64 deadline)
{
  (void) response;
  assert (session->phase == xos_file_session_active && deadline == 10000
          && request->operation == 8);
  ++startup_closes;
  return 0;
}
#ifdef XOS_ONLINE_CLOSURE
static long exchange (const struct xos_file_request *request,
                      struct xos_file_response *response, xos_u64 deadline)
{
  ++requests;
  assert (deadline == images.online_deadline && clock_value < deadline);
  assert (request->handle == 2 || request->handle == 3);
  if (poisoned) return -EIO;
  ++sends;
  if (fail_transport) { poisoned = 1; return -ETIMEDOUT; }
  memset (response, 0, sizeof *response);
  if (request->operation == 30)
    {
      response->length = request->length + (oversized != 0);
      memset (response->data, 'Q', response->length);
    }
  else
    {
      assert (request->operation == file_fstat);
      response->reserved = request->handle + (stale != 0);
      response->value = 64;
    }
  return 0;
}
static void *competitor (void *ignored)
{
  (void) ignored;
  thread = 2;
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == EBUSY);
  return NULL;
}
#endif
int main (void)
{
  struct xos_file_session session = { 17, 1, 68, 69, xos_file_session_active };
  struct xos_rtld_pin_plan plan = { .deadline_ns = 10000, .count = 3,
    .online_version = 1, .online_mask = 6, .isolated_mask = 2 };
  for (unsigned int i = 0; i < 3; ++i)
    {
      plan.pins[i] = (struct xos_rtld_pin) { .fd = 71 + (int) i, .handle = i + 1,
        .inode = i + 1, .file_bytes = 64, .bias = 0x140000000000ULL + i * 0x2000000,
        .reservation_budget = 4096, .commit_budget = 4096 };
      strcpy (plan.pins[i].soname, i == 0 ? "libc.so.0.1" : i == 1 ? "liba.so" : "libtls.so");
    }
  assert (xos_rtld_valid_pin_plan (&plan));
  struct xos_rtld_pin_plan invalid = plan;
  invalid.pins[1].fd = invalid.pins[0].fd + 32;
  assert (!xos_rtld_valid_pin_plan (&invalid));
  invalid = plan; invalid.online_reserved = 1; assert (!xos_rtld_valid_pin_plan (&invalid));
  invalid = plan; invalid.isolated_mask |= 1; assert (!xos_rtld_valid_pin_plan (&invalid));
  invalid = plan; invalid.online_version = 2; assert (!xos_rtld_valid_pin_plan (&invalid));
  invalid = plan; invalid.pins[1].fd = __INT_MAX__; assert (!xos_rtld_valid_pin_plan (&invalid));
  images.files = &session; images.plan = &plan;
#ifndef XOS_ONLINE_CLOSURE
  assert (__xos_rtld_attach_images (&images) == ENOTSUP);
  plan.online_version = plan.online_mask = plan.isolated_mask = 0;
  assert (__xos_rtld_attach_images (&images) == 0);
  assert (__xos_rtld_finish_images (&images) == 0 && startup_closes == 3);
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == ENOTSUP);
  puts ("K3_MAPPING_FIXED_DENIAL_PASS");
#else
  assert (__xos_rtld_attach_images (&images) == 0);
  plan.pins[1].handle = 200; /* The retained copy must survive the startup stack. */
  assert (__xos_rtld_finish_images (&images) == 0 && startup_closes == 1);
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == ENOTSUP);
  session.phase = xos_file_session_transferred;
  assert (__xos_rtld_enable_online (exchange) == 0);
  assert (__xos_rtld_online_begin ("new.so", 0, RTLD_NOW, 0) == ENOENT);
  assert (__xos_rtld_online_begin ("/liba.so", 0, RTLD_NOW, 0) == EINVAL);
  assert (__xos_rtld_online_begin ("libc.so.0.1", 0, RTLD_NOW, 0) == EPERM);
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_LAZY, 0) == ENOTSUP);
  assert (__xos_rtld_online_begin ("liba.so", 2, RTLD_NOW, 0) == ENOTSUP);
  assert (__xos_rtld_online_begin ("libtls.so", -1, RTLD_NOW, 0) == ENOTSUP);
  assert (!requests);
  process = 18; assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == EPERM); process = 17;
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == 0);
  const xos_u64 original_deadline = images.online_deadline;
  pthread_t other;
  assert (pthread_create (&other, NULL, competitor, NULL) == 0 && pthread_join (other, NULL) == 0);
  int base = __xos_rtld_open_pin_namespace ("liba.so", 0);
  int private = __xos_rtld_open_pin_namespace ("liba.so", 1);
  assert (base == 72 && private == 104);
  unsigned char bytes[8];
  assert (__xos_rtld_read_pin (base, bytes, sizeof bytes) == sizeof bytes && bytes[0] == 'Q');
  assert (__xos_rtld_read_pin (private, bytes, sizeof bytes) == sizeof bytes);
  assert (images.leases[1].cursor == 8 && images.leases[17].cursor == 8);
  assert (__xos_rtld_stat_pin (base) == 0);
  stale = 1; assert (__xos_rtld_stat_pin (base) == -ESTALE); stale = 0;
  oversized = 1; assert (__xos_rtld_read_pin (base, bytes, sizeof bytes) == -EIO); oversized = 0;
  const int previous = requests;
  assert (__xos_rtld_close_pin (base) == 0 && __xos_rtld_close_pin (private) == 0 && requests == previous);
  assert (__xos_rtld_open_pin ("liba.so") == base);
  for (int depth = 1; depth < 8; ++depth)
    assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == 0
            && images.online_deadline == original_deadline);
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == ELOOP);
  clock_value = original_deadline;
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == ETIMEDOUT);
  assert (__xos_rtld_read_pin (base, bytes, sizeof bytes) == -ETIMEDOUT && requests == previous);
  assert (__xos_rtld_close_pin (base) == 0);
  for (int depth = 0; depth < 8; ++depth) __xos_rtld_online_end ();
  assert (!images.online_owner && !images.online_depth);
  assert (__xos_rtld_online_begin ("liba.so", 0, RTLD_NOW, 0) == 0);
  base = __xos_rtld_open_pin ("liba.so");
  fail_transport = 1; const int before_sends = sends;
  assert (__xos_rtld_read_pin (base, bytes, sizeof bytes) == -ETIMEDOUT);
  assert (__xos_rtld_read_pin (base, bytes, sizeof bytes) == -EIO && sends == before_sends + 1);
  assert (__xos_rtld_close_pin (base) == 0); __xos_rtld_online_end ();
  puts ("K3_MAPPING_ONLINE_PASS approval retained_pin namespace gate recursion deadline poison close malformed_response");
#endif
}
