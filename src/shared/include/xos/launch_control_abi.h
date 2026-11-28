/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_LAUNCH_CONTROL_ABI_H
#define XOS_LAUNCH_CONTROL_ABI_H

/* Native x86-64 wire shared by the SDK and libc-independent bootstrap. */
#define XOS_LAUNCH_CONTROL_MAGIC 0x314c525443534f58ULL
#define XOS_LAUNCH_CONTROL_VERSION 1U
#define XOS_LAUNCH_CONTROL_MAX_NS 60000000000ULL
#define XOS_LAUNCH_PREPARE 1U
#define XOS_LAUNCH_ALLOW 2U
#define XOS_LAUNCH_READY 3U
#define XOS_LAUNCH_READY_ACK 4U
#define XOS_LAUNCH_FAILURE 5U
#define XOS_LAUNCH_FAILURE_ACK 6U
#define XOS_LAUNCH_CANCEL 7U
#define XOS_LAUNCH_CANCEL_ACK 8U
#define XOS_LAUNCH_PHASE_NONE 0U
#define XOS_LAUNCH_PHASE_PREPARE 1U
#define XOS_LAUNCH_PHASE_MAP 2U
#define XOS_LAUNCH_PHASE_RELOCATE 3U
#define XOS_LAUNCH_PHASE_INITIALIZE 4U
#define XOS_LAUNCH_PHASE_ENTRY 5U
#define XOS_LAUNCH_PHASE_COMMIT 6U

typedef struct xos_launch_descriptor {
    __UINT64_TYPE__ magic;
    __UINT32_TYPE__ version, size;
    __UINT64_TYPE__ controller_pid, child_pid, generation, nonce, deadline;
    __UINT32_TYPE__ ready_handle, ack_handle;
    __UINT64_TYPE__ reserved[2];
} xos_launch_descriptor;

typedef struct xos_launch_artifact {
    __UINT64_TYPE__ id;
    __UINT8_TYPE__ sha256[32];
} xos_launch_artifact;

typedef struct xos_launch_message {
    __UINT64_TYPE__ magic;
    __UINT32_TYPE__ version, size, type, phase;
    __UINT64_TYPE__ generation, nonce, pid, deadline;
    __INT64_TYPE__ status;
    xos_launch_artifact artifact;
    __UINT64_TYPE__ reserved[3];
} xos_launch_message;

#if defined(__cplusplus)
static_assert(sizeof(xos_launch_descriptor) == 80);
static_assert(sizeof(xos_launch_artifact) == 40);
static_assert(sizeof(xos_launch_message) == 128);
#else
_Static_assert(sizeof(xos_launch_descriptor) == 80, "launch descriptor ABI");
_Static_assert(sizeof(xos_launch_artifact) == 40, "launch artifact ABI");
_Static_assert(sizeof(xos_launch_message) == 128, "launch message ABI");
#endif
#endif
