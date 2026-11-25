/* SPDX-License-Identifier: Apache-2.0
   ELF-described read-only ranges are checked by the generic loader helper.
   Unknown ranges cannot be approved for fortified %n formatting. */
#include <stdlib.h>
enum readonly_error_type
__readonly_area_fallback (const void *pointer, size_t size)
{
  (void) pointer;
  (void) size;
  return readonly_area_writable;
}
