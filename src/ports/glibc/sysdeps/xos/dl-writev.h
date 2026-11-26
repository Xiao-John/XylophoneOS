/* SPDX-License-Identifier: Apache-2.0 */
#if defined SHARED && IS_IN (rtld)
# include <sys/uio.h>
# include "xos_console.h"

static inline ssize_t
xos_rtld_write (int fd, const void *buffer, size_t length)
{
  if (length > LONG_MAX)
    return -EINVAL;
  size_t written = 0;
  const char *text = buffer;
  while (written < length)
    {
      const size_t remaining = length - written;
      const size_t amount = remaining > 256 ? 256 : remaining;
      const long result = xos_console_raw (11, fd, (uintptr_t) (text + written), amount);
      if (result <= 0 || (size_t) result > amount)
        return written != 0 ? (ssize_t) written : -xos_console_errno (result);
      written += result;
    }
  return written;
}

/* The interpreter can report a failure before the libc FD table and TLS
   exist. Write through the inherited native output descriptor. */
static inline void
_dl_writev (int fd, const struct iovec *iov, size_t count)
{
  for (size_t i = 0; i < count; ++i)
    {
      const ssize_t written = xos_rtld_write (fd, iov[i].iov_base, iov[i].iov_len);
      if (written < 0 || (size_t) written != iov[i].iov_len)
        return;
    }
}
#else
# include_next <dl-writev.h>
#endif
