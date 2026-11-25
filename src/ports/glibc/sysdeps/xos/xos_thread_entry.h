/* SPDX-License-Identifier: Apache-2.0
   Private arguments for the XOS x86-64 thread entry trampoline.  */
#ifndef XOS_GLIBC_THREAD_ENTRY_H
#define XOS_GLIBC_THREAD_ENTRY_H 1

#define XOS_THREAD_ENTRY_RUN_OFFSET 0
#define XOS_THREAD_ENTRY_ARGUMENT_OFFSET 8

#ifndef __ASSEMBLER__
struct xos_thread_entry_args
{
  void (*run) (void *);
  void *argument;
};

# ifdef __cplusplus
extern "C" {
#  define XOS_THREAD_ENTRY_ASSERT static_assert
# else
#  define XOS_THREAD_ENTRY_ASSERT _Static_assert
# endif
XOS_THREAD_ENTRY_ASSERT (__builtin_offsetof (struct xos_thread_entry_args, run)
                        == XOS_THREAD_ENTRY_RUN_OFFSET, "XOS thread entry callback offset");
XOS_THREAD_ENTRY_ASSERT (__builtin_offsetof (struct xos_thread_entry_args, argument)
                        == XOS_THREAD_ENTRY_ARGUMENT_OFFSET, "XOS thread entry argument offset");
# undef XOS_THREAD_ENTRY_ASSERT

/* Pass this address and a fully initialized argument record to thread_start.
   The record must stay readable until the new thread loads both fields.
   The callback owns the thread's exit protocol and must never return.  */
__attribute__ ((visibility ("hidden"), noreturn))
void __xos_thread_entry (const struct xos_thread_entry_args *);
# ifdef __cplusplus
}
# endif
#endif
#endif
