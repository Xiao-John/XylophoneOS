/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_NET2_WIRE_H
#define XOS_GLIBC_NET2_WIRE_H 1
#include "xos_wait_word.h"

enum
{
  xos_net2_version = 2, xos_net2_header_bytes = 64, xos_net2_payload_bytes = 1024,
  xos_net2_tcp = 1, xos_net2_open = 2, xos_net2_status = 3, xos_net2_send = 4,
  xos_net2_receive = 5, xos_net2_close = 6, xos_net2_cancel = 7,
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

#endif
