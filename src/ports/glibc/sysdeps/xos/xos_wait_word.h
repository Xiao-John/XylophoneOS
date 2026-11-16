/* SPDX-License-Identifier: Apache-2.0
   Internal XOS wait-word ABI bridge.  This is not the glibc futex interface. */
#ifndef XOS_GLIBC_WAIT_WORD_H
#define XOS_GLIBC_WAIT_WORD_H 1

/* x86-64 LP64 XOS ABI; these types do not depend on another libc's headers. */
typedef __UINT32_TYPE__ xos_u32;
typedef __UINT64_TYPE__ xos_u64;
typedef __INT64_TYPE__ xos_i64;

#ifdef __cplusplus
# define XOS_WAIT_ASSERT static_assert
extern "C" {
#else
# define XOS_WAIT_ASSERT _Static_assert
#endif

struct xos_wait_word_request
{
  xos_u32 version;
  xos_u32 size;
  xos_u64 header_reserved;
  xos_u64 address;
  xos_u64 deadline_ns;
  xos_u32 expected;
  xos_u32 reserved;
};
XOS_WAIT_ASSERT (sizeof (struct xos_wait_word_request) == 40, "XOS wait ABI size");
XOS_WAIT_ASSERT (__builtin_offsetof (struct xos_wait_word_request, address) == 16,
                "XOS wait ABI address offset");
XOS_WAIT_ASSERT (__builtin_offsetof (struct xos_wait_word_request, expected) == 32,
                "XOS wait ABI expected offset");

/* Private, same-process waits only; absolute CLOCK_MONOTONIC deadline in ns,
   or UINT64_MAX for no deadline.  Return raw XOS results, not errno values.
   The caller must implement cancellation, error translation and lifetime. */
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_wait_word (xos_u32 *address, xos_u32 expected, xos_u64 deadline_ns);
__attribute__ ((visibility ("hidden")))
xos_i64 __xos_wake_word (xos_u32 *address, xos_u32 count);
#ifdef __cplusplus
}
#endif
#undef XOS_WAIT_ASSERT
#endif
