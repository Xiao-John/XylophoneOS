/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>

/* Two ordinary GCC TLS templates, with different alignment requirements. */
_Alignas (D1_TLS_ALIGNMENT) _Thread_local uint8_t initial[] = { D1_TLS_VALUE, 0x3c, 0x19 };
_Thread_local uint8_t zeroed[129];

uint64_t
d1_dependency (uint64_t value)
{
  return value + D1_TLS_VALUE;
}
