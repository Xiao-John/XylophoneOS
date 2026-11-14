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
static void test_tls_layout() {
  xos_thread_reservation r{};
  xos_thread_tls_layout out{11, 22, 33};
  r.tls_begin = 0x70000101; r.tls_end = 0x70002000;
  assert(__xos_thread_tls_layout(&r, 0x1100, 64, 0x400, &out) == 0);
  assert(out.thread_pointer == 0x70000e40 && out.static_begin == 0x70000140);
  assert(out.descriptor_end == 0x70001240);
  for (xos_u64 alignment = 16; alignment <= 4096; alignment *= 2) {
    for (xos_u64 begin = 1; begin < 128; ++begin) {
      r.tls_begin = begin; r.tls_end = begin + 0x10000;
      assert(__xos_thread_tls_layout(&r, 0x1000, alignment, 0x400, &out) == 0);
      assert(out.thread_pointer % alignment == 0 && out.static_begin >= r.tls_begin);
      assert(out.thread_pointer - out.static_begin == 0xc00);
      assert(out.descriptor_end - out.thread_pointer == 0x400 && out.descriptor_end <= r.tls_end);
    }
  }
  out = {11, 22, 33};
  r.tls_begin = 100; r.tls_end = 200;
  assert(__xos_thread_tls_layout(&r, 1000, 16, 16, &out) == -1);
  assert(__xos_thread_tls_layout(&r, 64, 24, 16, &out) == -1);
  assert(__xos_thread_tls_layout(&r, 64, 8, 16, &out) == -1);
  assert(__xos_thread_tls_layout(&r, 15, 16, 16, &out) == -1);
  assert(__xos_thread_tls_layout(&r, 64, 16, 15, &out) == -1);
  r.tls_begin = ~xos_u64{0} - 20; r.tls_end = ~xos_u64{0};
  assert(__xos_thread_tls_layout(&r, 48, 16, 16, &out) == -1);
  r.tls_begin = ~xos_u64{0} - 20; r.tls_end = ~xos_u64{0};
  assert(__xos_thread_tls_layout(&r, 16, 64, 16, &out) == -1);
  assert(out.static_begin == 11 && out.thread_pointer == 22 && out.descriptor_end == 33);
}
int main() {
  test_tls_layout();
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
