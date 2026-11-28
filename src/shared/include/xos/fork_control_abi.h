/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_FORK_CONTROL_ABI_H
#define XOS_FORK_CONTROL_ABI_H 1
#include <xos/launch_control_abi.h>

/* A separate, parent-issued offer on a fresh fork child's ACK channel.
   It never aliases launch-message reserved fields or transfers the parent's
   own upstream controller. Native channel metadata authenticates both ends. */
#define XOS_FORK_CONTROL_MAGIC 0x314b524f46534f58ULL
#define XOS_FORK_CONTROL_VERSION 1U
typedef struct xos_fork_control_offer {
    __UINT64_TYPE__ magic;
    __UINT32_TYPE__ version, size;
    __UINT64_TYPE__ controller_pid, child_pid, generation, nonce, deadline;
    __UINT32_TYPE__ ready_handle, ack_handle;
    xos_launch_artifact artifact;
    __UINT64_TYPE__ reserved[3];
} xos_fork_control_offer;
#ifdef __cplusplus
static_assert(sizeof(xos_fork_control_offer) == 128);
#else
_Static_assert(sizeof(xos_fork_control_offer) == 128, "fork control offer v1");
#endif
#endif
