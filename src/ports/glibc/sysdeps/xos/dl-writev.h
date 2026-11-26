/* SPDX-License-Identifier: Apache-2.0 */
#if defined SHARED && IS_IN (rtld)
# include <sys/uio.h>
# include "xos_file_trap.h"

/* The interpreter can report a failure before the libc FD table and TLS
   exist. Write through the inherited native output descriptor. */
static inline void
_dl_writev (int fd, const struct iovec *iov, size_t count)
{
  for (size_t i = 0; i < count; ++i)
    {
      const char *text = iov[i].iov_base;
      size_t remaining = iov[i].iov_len;
      while (remaining != 0)
        {
          const size_t bytes = remaining > 256 ? 256 : remaining;
          const long result = file_trap (11, fd, (xos_u64) text, bytes);
          if (result <= 0 || (size_t) result > bytes)
            return;
          text += result;
          remaining -= result;
        }
    }
}
#else
# include_next <dl-writev.h>
#endif
