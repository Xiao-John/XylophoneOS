/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_wait_word.h"
#include <xos/thread_abi.hpp>

static xos_u64 last_number, last_first, last_second;
static struct xos_wait_word_request observed;
static xos_i64 next_result;
extern "C" xos_i64 __xos_wait_test_call (xos_u64 number, xos_u64 first, xos_u64 second)
{
  last_number = number; last_first = first; last_second = second;
  if (number == xos::sys_wait_word) observed = *(const struct xos_wait_word_request *) first;
  return next_result;
}
static_assert (sizeof (struct xos_wait_word_request) == sizeof (xos::thread_wait_request));
static_assert (__builtin_offsetof (struct xos_wait_word_request, deadline_ns) ==
               __builtin_offsetof (xos::thread_wait_request, deadline_ns));
static_assert (__builtin_offsetof (struct xos_wait_word_request, reserved) ==
               __builtin_offsetof (xos::thread_wait_request, reserved));
int main ()
{
  xos_u32 word = 7;
  next_result = xos::thread_value_changed;
  if (__xos_wait_word (&word, 7, xos::thread_deadline_infinite) != next_result) return 1;
  if (last_number != xos::sys_wait_word || last_second != 0 ||
      observed.version != xos::thread_abi_version || observed.size != sizeof (observed) ||
      observed.header_reserved || observed.reserved || observed.address != (xos_u64) &word ||
      observed.expected != 7 || observed.deadline_ns != xos::thread_deadline_infinite) return 2;
  next_result = xos::thread_error_timeout;
  if (__xos_wait_word (&word, 99, 123456) != next_result || observed.deadline_ns != 123456 ||
      observed.expected != 99) return 3;
  next_result = 2;
  if (__xos_wake_word (&word, 3) != 2 || last_number != xos::sys_wake_word ||
      last_first != (xos_u64) &word || last_second != 3) return 4;
  next_result = xos::thread_error_address;
  if (__xos_wake_word (&word, 0) != next_result || last_second != 0) return 5;
  return 0;
}
