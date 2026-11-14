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
extern "C" xos_i64 __xos_thread_test_call(xos_u64 nr, xos_u64 first, xos_u64 second) {
  ++calls;
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
}
