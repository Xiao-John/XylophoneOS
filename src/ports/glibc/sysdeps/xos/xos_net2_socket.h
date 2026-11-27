/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_GLIBC_NET2_SOCKET_H
#define XOS_GLIBC_NET2_SOCKET_H 1
#include <stddef.h>
#include <poll.h>
#include "xos_wait_word.h"

enum { xos_net2_local_sockets = 32 };
long __xos_net2_alloc (void) __attribute__ ((visibility ("hidden")));
void __xos_net2_retire (unsigned int) __attribute__ ((visibility ("hidden")));
void __xos_net2_reap (void) __attribute__ ((visibility ("hidden")));
void __xos_net2_after_fork (void) __attribute__ ((visibility ("hidden")));
long __xos_net2_connect_fd (int, xos_u32, unsigned int)
  __attribute__ ((visibility ("hidden")));
long __xos_net2_stream (unsigned int, void *, size_t, int)
  __attribute__ ((visibility ("hidden")));
long __xos_net2_stream_fd (int, void *, size_t, int)
  __attribute__ ((visibility ("hidden")));
long __xos_net2_shutdown_fd (int, int)
  __attribute__ ((visibility ("hidden")));
long __xos_net2_poll (struct pollfd *, nfds_t, int)
  __attribute__ ((visibility ("hidden")));
#endif
