/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_RTLD_LOADER_IO_H
#define XOS_RTLD_LOADER_IO_H
#include <errno.h>
#include <fcntl.h>
#include <sys/types.h>
#include "xos_rtld_mapping.h"

/* Translate only for GNU rtld's own errno and descriptor plumbing. The
   actual requests run through the TLS-free private phase state. */
static inline long
xos_rtld_loader_result (long result)
{
  if (result >= 0)
    return result;
  __set_errno (-result);
  return -1;
}

static inline int
dl_load_open (const char *name, int flags)
{
  if (flags != (O_RDONLY | O_CLOEXEC))
    return xos_rtld_loader_result (-ENOTSUP);
  return xos_rtld_loader_result (__xos_rtld_open_pin (name));
}

static inline int
dl_load_open_namespace (const char *name, int flags, long ns)
{
  if (flags != (O_RDONLY | O_CLOEXEC))
    return xos_rtld_loader_result (-ENOTSUP);
  return xos_rtld_loader_result (__xos_rtld_open_pin_namespace (name, ns));
}

static inline ssize_t
dl_load_read (int fd, void *bytes, size_t size)
{
  if (size > UINT32_MAX)
    return xos_rtld_loader_result (-EINVAL);
  return xos_rtld_loader_result (__xos_rtld_read_pin (fd, bytes, size));
}

static inline ssize_t
dl_load_pread (int fd, void *bytes, size_t size, off64_t offset)
{
  if (size > UINT32_MAX)
    return xos_rtld_loader_result (-EINVAL);
  return xos_rtld_loader_result (__xos_rtld_pread_pin (fd, bytes, size, offset));
}

static inline int
dl_load_close (int fd)
{
  return xos_rtld_loader_result (__xos_rtld_close_pin (fd));
}

static inline bool
dl_load_check_pin (int fd)
{
  return xos_rtld_loader_result (__xos_rtld_stat_pin (fd)) == 0;
}
#endif
