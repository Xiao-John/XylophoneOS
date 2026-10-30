// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>
#include <sys/types.h>
#include <limits.h>
#ifndef SSIZE_MAX
#define SSIZE_MAX LONG_MAX
#endif
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#define BYTE_ORDER LITTLE_ENDIAN
#define LWIP_PLATFORM_DIAG(x) do { printf x; } while (0)
#define LWIP_PLATFORM_ASSERT(x) do { fprintf(stderr,"lwIP assertion: %s\n",x); abort(); } while (0)
// Required real entropy/time hooks deliberately remain unresolved in the archive.
// The service implementation must bind them to XOS random_bytes/monotonic clock.
uint32_t xos_lwip_random(void);
#define LWIP_RAND() xos_lwip_random()
