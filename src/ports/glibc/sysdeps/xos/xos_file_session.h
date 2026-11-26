/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_SESSION_H
#define XOS_GLIBC_FILE_SESSION_H 1
#include "xos_file_wire.h"

#ifdef __cplusplus
extern "C" {
#endif

enum { file_stat = 3, file_open = 4, file_fstat = 18, file_anonymous = 21,
       file_anonymous_seal = 22, file_cwd_set = 26, file_cwd_get = 27 };

enum xos_file_session_phase
{
  xos_file_session_active = 0,
  xos_file_session_failed = 1,
  xos_file_session_transferred = 2
};

/* Private process-local transport state. Zero initializes an unused session.
   Bootstrap may use it before TLS, with exactly one owner and no concurrent
   callers. The late runtime serializes it with its existing session lock. */
struct xos_file_session
{
  xos_u64 owner_pid;
  xos_u32 request_sequence, send_handle, receive_handle, phase;
};

/* Uses the supplied disjoint records as scratch space. The response is usable
   only after success. On a transport error, later calls fail closed. */
long __xos_file_session_call (struct xos_file_session *, struct xos_file_request *,
                             struct xos_file_response *)
  __attribute__ ((visibility ("hidden")));
/* Startup uses the same session with a shorter, absolute monotonic deadline.
   An already expired call sends nothing. If a sent request times out, the
   shared session is poisoned, as it is for an ordinary request timeout. */
long __xos_file_session_call_until (struct xos_file_session *, struct xos_file_request *,
                                   struct xos_file_response *, xos_u64)
  __attribute__ ((visibility ("hidden")));
long __xos_file_session_poison (struct xos_file_session *, int)
  __attribute__ ((visibility ("hidden")));
long __xos_file_session_take (struct xos_file_session *, struct xos_file_session *)
  __attribute__ ((visibility ("hidden")));
long __xos_file_service_error (int) __attribute__ ((visibility ("hidden")));

/* One-way handoff into the actual G3 backend before FD initialization. The
   source is consumed even when its authenticated session has already failed.
   Existing kernel-supplied startup records still own inherited descriptors. */
long __xos_file_adopt_early_session (struct xos_file_session *)
  __attribute__ ((visibility ("hidden")));

#ifdef __cplusplus
}
#endif
#endif
