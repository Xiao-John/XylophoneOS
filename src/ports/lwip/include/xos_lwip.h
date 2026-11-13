/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_LWIP_H
#define XOS_LWIP_H
#include <stdarg.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t xos_lwip_rand(void);
void xos_lwip_diag(const char* format, ...);
int net_ping_main(void);
#ifdef __cplusplus
}
#endif
#endif
