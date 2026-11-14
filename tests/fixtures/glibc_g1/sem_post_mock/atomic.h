/* SPDX-License-Identifier: Apache-2.0 */
#define atomic_load_relaxed(p) __atomic_load_n ((p), __ATOMIC_RELAXED)
#define atomic_compare_exchange_weak_release(p, expected, value) \
  __atomic_compare_exchange_n ((p), (expected), (value), 1, __ATOMIC_RELEASE, __ATOMIC_RELAXED)
