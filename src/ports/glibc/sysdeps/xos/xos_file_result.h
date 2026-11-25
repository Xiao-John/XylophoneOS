/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_FILE_RESULT_H
#define XOS_GLIBC_FILE_RESULT_H 1
#include <errno.h>
#include "xos_file_runtime.h"
static inline long
xos_file_result (long result)
{
  if (result < 0) { __set_errno ((int) -result); return -1; }
  return result;
}
#endif
