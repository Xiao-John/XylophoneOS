/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_NETWORK_ARCH_CC_H
#define XOS_NETWORK_ARCH_CC_H
#include "../../../../ports/lwip/include/arch/cc.h"
/* NO_SYS only needs signed size arithmetic; no POSIX headers or libc ctype
 * globals are needed by this service. Keep the port freestanding. */
typedef ptrdiff_t ssize_t;
#define LWIP_NO_UNISTD_H 1
#define LWIP_NO_CTYPE_H 1
/* Private adapter hook; a failed entropy read is separate from the value 0. */
#ifdef __cplusplus
extern "C" {
#endif
int xos_lwip_dns_random(uint16_t* value);
#ifdef __cplusplus
}
#endif
#endif
