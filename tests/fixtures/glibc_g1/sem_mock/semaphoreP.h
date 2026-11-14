/* SPDX-License-Identifier: Apache-2.0 */
#ifndef TEST_SEMAPHORE_P_H
#define TEST_SEMAPHORE_P_H
#include <errno.h>
#include <stdint.h>
#include <bits/local_lim.h>
#define __glibc_unlikely(x) (x)
#define __set_errno(x) (errno = (x))
#define ASSERT_PTHREAD_INTERNAL_SIZE(a, b) _Static_assert (sizeof (a) >= sizeof (b), "storage")
#define USE_64B_ATOMICS_ON_SEM_T 1
#define FUTEX_PRIVATE 0
#define FUTEX_SHARED 128
struct new_sem { uint64_t data; int private; };
#endif
