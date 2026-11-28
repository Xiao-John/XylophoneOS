/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_RUNTIME_H
#define XOS_GLIBC_FILE_RUNTIME_H 1
#include "xos_file_session.h"
#include <stddef.h>
#include <sys/stat.h>
#ifdef __cplusplus
extern "C" {
#endif

/* Return a nonnegative result or negative libc errno, without touching TLS. */
long __xos_file_open (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_open_anonymous (void) __attribute__ ((visibility ("hidden")));
long __xos_file_seal_anonymous (int) __attribute__ ((visibility ("hidden")));
long __xos_file_close (int) __attribute__ ((visibility ("hidden")));
long __xos_file_close_range (unsigned int, unsigned int) __attribute__ ((visibility ("hidden")));
long __xos_file_pipe (int [2], int) __attribute__ ((visibility ("hidden")));
long __xos_file_socket (int) __attribute__ ((visibility ("hidden")));
long __xos_file_read (int, void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_write (int, const void *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_seek (int, long, int) __attribute__ ((visibility ("hidden")));
long __xos_file_stat (int, const char *, struct stat *) __attribute__ ((visibility ("hidden")));
long __xos_file_getcwd (char *, size_t) __attribute__ ((visibility ("hidden")));
long __xos_file_chdir (const char *) __attribute__ ((visibility ("hidden")));
long __xos_file_access (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_dup (int, int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_fcntl (int, int, int) __attribute__ ((visibility ("hidden")));
long __xos_file_path_op (const char *, int) __attribute__ ((visibility ("hidden")));
long __xos_file_truncate (int, long) __attribute__ ((visibility ("hidden")));
long __xos_file_sync (int) __attribute__ ((visibility ("hidden")));
long __xos_file_isatty (int) __attribute__ ((visibility ("hidden")));
long __xos_file_fork (void) __attribute__ ((visibility ("hidden")));

/* Keep the native stdio routes and cwd stable until loader commit or abort. */
struct xos_spawn_stdio
{
  int object[3];
  long route[3];
  xos_u32 file_handle[3], open_flags[3];
};
long __xos_file_spawn_begin (struct xos_spawn_stdio *) __attribute__ ((visibility ("hidden")));
void __xos_file_spawn_end (struct xos_spawn_stdio *) __attribute__ ((visibility ("hidden")));

struct xos_exec_descriptors {
  struct xos_file_startup_descriptor items[32];
  xos_u32 count, retained[32], terminal_channels[2];
  xos_u64 terminal_sequence;
  int terminal_locked;
};
long __xos_file_exec_begin (struct xos_exec_descriptors *, xos_u64)
  __attribute__ ((visibility ("hidden")));
void __xos_file_exec_end (struct xos_exec_descriptors *, xos_u64)
  __attribute__ ((visibility ("hidden")));

/* Internal users retain an open description, never a reusable FD number.
   access is -1 for metadata, 0 for reading or 1 for writing. */
enum xos_file_kind
{
  xos_file_kind_kernel = 1, xos_file_kind_file = 2,
  xos_file_kind_pipe_read = 3, xos_file_kind_pipe_write = 4,
  xos_file_kind_terminal = 5, xos_file_kind_socket = 6
};
struct xos_file_lease { int object; unsigned int kind, handle, flags; };
long __xos_file_lease_acquire (int, int, struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
long __xos_file_lease_release (struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
/* Poll must not enter a file RPC or a deferred network close while acquiring
   or dropping a description. Initialization remains an ordinary FD operation. */
long __xos_file_poll_lease_acquire (int, struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
void __xos_file_poll_lease_release (struct xos_file_lease *)
  __attribute__ ((visibility ("hidden")));
long __xos_file_request_path (struct xos_file_request *, const char *)
  __attribute__ ((visibility ("hidden")));
/* Serialized files exchange: one request ID and one failure latch shared by
   all libc and native-loader users of this process's authenticated session.
   Cwd changes targeting this process also serialize against native spawn.
   The output is cleared before exchange and remains empty on failure. */
long __xos_file_exchange (const struct xos_file_request *, struct xos_file_response *)
  __attribute__ ((visibility ("hidden")));
/* Native loader hook uses file::status values, not libc errno values. */
long xos_file_session_exchange (const struct xos_file_request *, struct xos_file_response *)
  __attribute__ ((visibility ("hidden")));
/* Includes cwd/session lock acquisition and startup descriptor initialization.
   The finite absolute deadline expires as SDK transport_timeout (-1001),
   distinct from every files-v2 status. Shares the same sequence and poison. */
long xos_file_session_exchange_until (const struct xos_file_request *,
                                    struct xos_file_response *, xos_u64)
  __attribute__ ((visibility ("hidden")));
#ifdef __cplusplus
}
#endif
#endif
