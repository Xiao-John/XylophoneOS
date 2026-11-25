/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_RUNTIME_H
#define XOS_GLIBC_FILE_RUNTIME_H 1
#include "xos_file_wire.h"
#include <stddef.h>
#include <sys/stat.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Return a nonnegative result or negative libc errno, without touching TLS. */
long __xos_file_open (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_close (int) __attribute__ ((visibility ("hidden")));
long __xos_file_read (int, void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_write (int, const void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_seek (int, long, int) __attribute__ ((visibility ("hidden")));
long __xos_file_stat (int, const char *, struct stat *) __attribute__ ((visibility ("hidden")));
long __xos_file_dup (int, int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_fcntl (int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_path_op (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_truncate (int, long) __attribute__ ((visibility ("hidden")));
long __xos_file_sync (int) __attribute__ ((visibility ("hidden")));
long __xos_file_isatty (int) __attribute__ ((visibility ("hidden")));

/* Internal users retain an open description, never a reusable FD number.
   access is -1 for metadata, 0 for reading or 1 for writing. */
enum xos_file_kind
{
  xos_file_kind_kernel = 1, xos_file_kind_file = 2,
  xos_file_kind_pipe_read = 3, xos_file_kind_pipe_write = 4
};
struct xos_file_lease { int object; unsigned int kind, handle, flags; };
long __xos_file_lease_acquire (int, int, struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
long __xos_file_lease_release (struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
long __xos_file_request_path (struct xos_file_request *, const char *)
  __attribute__ ((visibility ("hidden")));
/* Serialized files exchange: one request ID and one failure latch shared by
   all libc and native-loader users of this process's authenticated session.
   The output is cleared before exchange and remains empty on failure. */
long __xos_file_exchange (const struct xos_file_request *, struct xos_file_response *)
  __attribute__ ((visibility ("hidden")));
/* Native loader hook uses file::status values, not libc errno values. */
long xos_file_session_exchange (const struct xos_file_request *, struct xos_file_response *)
  __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
