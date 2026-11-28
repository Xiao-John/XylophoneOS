/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_DYNAMIC_STARTUP_ABI_H
#define XOS_DYNAMIC_STARTUP_ABI_H
#include <xos/launch_control_abi.h>
#define XOS_DYNAMIC_STARTUP_ADDRESS 0x70000000ULL
#define XOS_DYNAMIC_STARTUP_MAGIC 0x3150555453594458ULL
#define XOS_DYNAMIC_STARTUP_VERSION 1U
typedef struct xos_dynamic_startup_prefix {
    __UINT64_TYPE__ magic;
    __UINT32_TYPE__ version, size;
    xos_launch_descriptor control;
    xos_launch_artifact artifact;
    __UINT64_TYPE__ reserved[3];
} xos_dynamic_startup_prefix;
#if defined(__cplusplus)
static_assert(sizeof(xos_dynamic_startup_prefix) == 160);
#else
_Static_assert(sizeof(xos_dynamic_startup_prefix) == 160, "dynamic startup ABI");
#endif
#endif
