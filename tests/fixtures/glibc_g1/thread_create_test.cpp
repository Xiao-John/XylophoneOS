// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <cstddef>
#include <cstring>
#include <xos/thread_abi.hpp>
#include "xos_thread_create.h"

static_assert(sizeof(xos_thread_prepare_request) == sizeof(xos::thread_prepare_request));
static_assert(sizeof(xos_thread_reservation) == sizeof(xos::thread_reservation));
static_assert(sizeof(xos_thread_start_request) == sizeof(xos::thread_start_request));
static_assert(offsetof(xos_thread_prepare_request, flags) == offsetof(xos::thread_prepare_request, flags));
static_assert(offsetof(xos_thread_reservation, tls_end) == offsetof(xos::thread_reservation, tls_end));
static_assert(offsetof(xos_thread_start_request, thread_pointer) == offsetof(xos::thread_start_request, thread_pointer));
static xos_i64 answer;
static int calls;
static bool launch_mode;
static xos_i64 prepare_error, start_error, abort_error, setup_error;
static xos_thread_launch_result *observed;
static int setup_calls, abort_calls, start_calls;
extern "C" xos_i64 __xos_thread_test_call(xos_u64 nr, xos_u64 first, xos_u64 second) {
  ++calls;
  if (launch_mode) {
    if (nr == xos::sys_thread_prepare) answer = prepare_error;
    else if (nr == xos::sys_thread_start) {
      ++start_calls;
      assert(__atomic_load_n(&observed->tid, __ATOMIC_ACQUIRE) == 17);
      answer = start_error;
    } else { ++abort_calls; answer = abort_error; }
  }
  if (nr == xos::sys_thread_prepare) {
    xos::thread_prepare_request req;
    std::memcpy(&req, reinterpret_cast<void *>(first), sizeof req);
    assert(req.header.version == 1 && req.header.size == sizeof req && req.header.reserved == 0);
    assert(req.stack_bytes == 65536 && req.tls_bytes == 512 && req.flags == 1);
    if (answer == 0) {
      xos::thread_reservation result{{1, sizeof(result), 0}, 17, 10, 20, 30, 40};
      std::memcpy(reinterpret_cast<void *>(second), &result, sizeof result);
    }
  } else if (nr == xos::sys_thread_start) {
    xos::thread_start_request req;
    std::memcpy(&req, reinterpret_cast<void *>(first), sizeof req);
    assert(req.header.version == 1 && req.header.size == sizeof req && req.header.reserved == 0);
    assert(req.tid == 17 && req.entry == 21 && req.argument == 22 && req.stack == 32 && req.thread_pointer == 48);
    assert(second == 0);
  } else {
    assert(nr == xos::sys_thread_abort && first == 17 && second == 0);
  }
  return answer;
}
static xos_i64 setup(const xos_thread_reservation *r, xos_thread_start_parameters *p, void *) {
  ++setup_calls;
  assert(r->tid == 17 && __atomic_load_n(&observed->tid, __ATOMIC_ACQUIRE) == 17);
  *p = {21, 22, 32, 48};
  return setup_error;
}
int main() {
  xos_thread_reservation reservation{};
  answer = -17;
  assert(__xos_thread_prepare(65536, 512, 1, &reservation) == -17 && reservation.tid == 0);
  answer = 0;
  assert(__xos_thread_prepare(65536, 512, 1, &reservation) == 0 && reservation.tid == 17);
  answer = -2;
  assert(__xos_thread_start(17, 21, 22, 32, 48) == -2);
  answer = -12;
  assert(__xos_thread_abort(17) == -12);
  answer = 0;
  assert(__xos_thread_abort(17) == 0);
  assert(__xos_thread_start(17, 21, 22, 32, 48) == 0);
  assert(calls == 6);
  launch_mode = true;
  xos_thread_launch_result result{};
  observed = &result;
  prepare_error = -17;
  assert(__xos_thread_launch(65536, 512, 1, setup, nullptr, &result) == -17);
  assert(result.tid == 0 && result.abort_error == 0 && !result.started && setup_calls == 0 && abort_calls == 0);
  prepare_error = 0; setup_error = -2;
  assert(__xos_thread_launch(65536, 512, 1, setup, nullptr, &result) == -2);
  assert(result.tid == 0 && result.abort_error == 0 && !result.started && start_calls == 0 && abort_calls == 1);
  setup_error = 0; start_error = -2; abort_error = -12;
  assert(__xos_thread_launch(65536, 512, 1, setup, nullptr, &result) == -2);
  assert(result.tid == 17 && result.abort_error == -12 && !result.started && start_calls == 1 && abort_calls == 2);
  abort_error = 0;
  assert(__xos_thread_launch(65536, 512, 1, setup, nullptr, &result) == -2);
  assert(result.tid == 0 && result.abort_error == 0 && !result.started && start_calls == 2 && abort_calls == 3);
  start_error = 0;
  assert(__xos_thread_launch(65536, 512, 1, setup, nullptr, &result) == 0);
  assert(result.tid == 17 && result.abort_error == 0 && result.started && start_calls == 3 && abort_calls == 3);
}
