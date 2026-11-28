/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_NET2_WIRE_H
#define XOS_GLIBC_NET2_WIRE_H 1
#include "xos_wait_word.h"

enum
{
  xos_net2_version = 2, xos_net2_header_bytes = 64, xos_net2_payload_bytes = 1024,
  xos_net2_tcp = 1, xos_net2_open = 2, xos_net2_status = 3, xos_net2_send = 4,
  xos_net2_receive = 5, xos_net2_close = 6, xos_net2_cancel = 7,
  xos_net2_capabilities = 15, xos_net2_readiness = 16, xos_net2_shutdown_write = 17,
  xos_net2_extension_revision = 1, xos_net2_cap_readiness = 1, xos_net2_cap_shutdown_write = 2,
  xos_net2_ready_read = 1, xos_net2_ready_write = 2, xos_net2_ready_eof = 4,
  xos_net2_ready_error = 8, xos_net2_ready_write_closed = 16, xos_net2_ready_connecting = 32,
  xos_net2_connecting = 1, xos_net2_connected = 2, xos_net2_eof = 4, xos_net2_failed = 8,
  xos_net2_invalid = -201, xos_net2_denied = -202, xos_net2_resources = -203,
  xos_net2_again = -204, xos_net2_timeout = -205, xos_net2_closed = -206,
  xos_net2_io = -207, xos_net2_unsupported = -208, xos_net2_buffer = -209,
  xos_net2_reset = -210
};

/* C representation of the existing xos::net2::message. */
struct xos_net2_message
{
  xos_u32 version, action;
  xos_u64 sequence, object, deadline;
  xos_i64 result;
  xos_u32 address;
  __UINT16_TYPE__ port, transport;
  xos_u32 length, flags;
  xos_u64 reserved;
  unsigned char data[xos_net2_payload_bytes];
};
struct xos_net2_capability_snapshot { xos_u32 revision, flags; xos_u64 reserved; };
struct xos_net2_readiness_snapshot
{
  xos_u64 generation;
  xos_u32 events, readable_bytes, writable_bytes, reserved;
  xos_i64 error;
};

#endif
