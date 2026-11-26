/* SPDX-License-Identifier: Apache-2.0 */
#if defined SHARED && IS_IN (rtld)
# include <ldsodefs.h>
# include <dl-writev.h>

ssize_t
_dl_write (int fd, const void *buffer, size_t length)
{
  return xos_rtld_write (fd, buffer, length);
}
#else
# include <elf/dl-write.c>
#endif
