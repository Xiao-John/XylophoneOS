/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_DIRSTREAM_H
#define XOS_GLIBC_DIRSTREAM_H 1
#include "xos_file_runtime.h"
/* Private libc state. A lease retains the original directory independently
   of FD-number reuse; the bounded page is a live view, not a snapshot. */
struct __dirstream
{
  int fd;
  xos_u32 lock;
  struct xos_file_lease lease;
  xos_u32 cursor, page_length, page_position, page_next;
  int end;
  union { xos_u64 alignment; unsigned char bytes[512]; } entry;
  unsigned char page[3798];
};
#endif
