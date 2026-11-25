/* SPDX-License-Identifier: Apache-2.0 */
#include "../../../ports/lwip/include/lwipopts.h"
/* Match the native service's eight-connection quota for both transports. */
#define MEMP_NUM_UDP_PCB 8
/* pbuf/PCB contain native 64-bit pointers on this target. */
#define MEM_ALIGNMENT 8
/* Assertion failures take the normal process fault/cleanup path. */
#undef LWIP_PLATFORM_ASSERT
#define LWIP_PLATFORM_ASSERT(message) do { (void)(message); __builtin_trap(); } while (0)
