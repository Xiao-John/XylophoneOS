/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#define USE_64B_ATOMICS_ON_SEM_T 1
#define SEM_VALUE_MASK (~(unsigned int)0)
#define SEM_NWAITERS_SHIFT 32
#define SEM_VALUE_OFFSET 0
struct new_sem { uint64_t data; int private; int pad; };
