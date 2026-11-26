// SPDX-License-Identifier: Apache-2.0
#include <stdint.h>

static uint64_t word = 0x4090;
static uint64_t scratch[1024];
static uint64_t *const word_pointer = &word;

__attribute__((visibility("default")))
uint64_t d1_entry(uint64_t delta)
{
    uint64_t *target = *(uint64_t *const volatile *)&word_pointer;
    uint64_t previous = scratch[delta & 1023];
    uint64_t result = *target + previous + delta;
    *target = result;
    scratch[delta & 1023] = delta;
    return result;
}
