/* SPDX-License-Identifier: Apache-2.0 */
#include "xos_thread_exit.h"
#include <xos/thread_abi.hpp>
#include <setjmp.h>

static jmp_buf done;
static long begin_result;
static unsigned calls;
static unsigned last_calls;
static unsigned long numbers[3], arguments[3];
extern "C" long __xos_thread_test_trap (unsigned long number, unsigned long argument)
{
  numbers[calls] = number;
  arguments[calls++] = argument;
  if (calls == 1) return begin_result;
  if (calls == 2) longjmp (done, 1);
  return -1;
}
static void final_exit ()
{
  ++last_calls;
  longjmp (done, 1);
}
static int run_case (long begin, unsigned long terminal, unsigned long status)
{
  begin_result = begin;
  calls = 0;
  if (setjmp (done) == 0) __xos_internal_exit (5);
  return calls == 2 && numbers[0] == xos::sys_thread_begin_exit && arguments[0] == 0
         && numbers[1] == terminal && arguments[1] == status;
}
int main ()
{
  if (!run_case (0, xos::sys_thread_exit, 5)) return 1;
  if (!run_case (1, 2, 127)) return 2;
  if (!run_case (xos::process_error_state, 2, 127)) return 3;
  calls = 0;
  begin_result = 0;
  constexpr unsigned long wide_result = 0xfedcba9876543210UL;
  if (setjmp (done) == 0) __xos_thread_finish (wide_result, final_exit);
  if (calls != 2 || numbers[1] != xos::sys_thread_exit
      || arguments[1] != wide_result || last_calls != 0) return 4;
  calls = 0;
  begin_result = 1;
  if (setjmp (done) == 0) __xos_thread_finish (wide_result, final_exit);
  if (calls != 1 || last_calls != 1) return 5;
  return 0;
}
