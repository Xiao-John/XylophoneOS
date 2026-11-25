/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_PROCESS_EXIT_H
#define XOS_GLIBC_PROCESS_EXIT_H 1

struct xos_process_exit_cleanup_request
{
  __UINT32_TYPE__ version, size;
  __UINT64_TYPE__ header_reserved, deadline_ns;
  __INT32_TYPE__ timeout_status;
  __UINT32_TYPE__ reserved;
};
#ifdef __cplusplus
static_assert (sizeof (xos_process_exit_cleanup_request) == 32,
               "XOS process cleanup ABI size");
extern "C" {
#else
_Static_assert (sizeof (struct xos_process_exit_cleanup_request) == 32,
                "XOS process cleanup ABI size");
#endif

/* Return only for the elected cleanup owner. Other exit callers block until
   the owner finishes or the kernel enforces the original cleanup deadline. */
__attribute__ ((visibility ("hidden"))) void __xos_process_exit_begin (void);

#ifdef __cplusplus
}
#endif
#endif
