/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>

static volatile uint64_t cells[D1_BSS_WORDS];

__attribute__ ((visibility ("default"))) uint64_t
d1_dependency (uint64_t input)
{
  unsigned int index = input & (D1_BSS_WORDS - 1);
  uint64_t previous = cells[index];
  cells[index] = input;
  return 0xd100 + input + previous;
}
