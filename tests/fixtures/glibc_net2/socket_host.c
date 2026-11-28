/* SPDX-License-Identifier: Apache-2.0 */
/* Actual libc Net2 bridge; only the authenticated IPC/FD boundary is injected. */
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include "xos_file_runtime.h"
#include "xos_net2_socket.h"
#include "xos_net2_wire.h"

static struct xos_net2_message request;
static xos_u64 now = 100000000, ready_after, next_handle = 17, last_handle;
static unsigned int route_for_fd[32], leases, calls[21], closes;
static int old_server, malformed, move_fd_on_sleep, no_reply, legacy_kernel;
static int page_mode, freeze_page, nonblocking, pending_connect, closed_read, closed_write;
static int release_error, move_fd_on_reply, current_busy, busy_after_reply;
static unsigned int release_attempts, name_connections;
static struct xos_net2_readiness_page shared_page;
static struct xos_net2_readiness_snapshot model_readiness (void)
{
  struct xos_net2_readiness_snapshot snapshot = { .generation = 1 };
  if (!closed_write && !pending_connect) { snapshot.events |= xos_net2_ready_write; snapshot.writable_bytes = 71; }
  if (closed_write) snapshot.events |= xos_net2_ready_write_closed;
  if (pending_connect) snapshot.events |= xos_net2_ready_connecting;
  if (ready_after && now >= ready_after) { snapshot.events |= xos_net2_ready_read; snapshot.readable_bytes = 13; }
  if (closed_read) { snapshot.events |= xos_net2_ready_read | xos_net2_ready_eof | xos_net2_ready_read_closed; snapshot.readable_bytes = 0; }
  if (malformed) snapshot.reserved = 1;
  return snapshot;
}
static void publish_page (void)
{
  if (!page_mode || freeze_page) return;
  shared_page.sequence += 2; shared_page.revision = 1; shared_page.session_generation = 13;
  shared_page.sampled_ns = now; shared_page.count = 0;
  for (xos_u64 handle = 17; handle < next_handle; ++handle)
    shared_page.records[shared_page.count++] = (struct xos_net2_readiness_record) { .handle = handle, .ready = model_readiness () };
}
static int advance_page_on_peer;

long __xos_wait_word (xos_u32 *address, xos_u32 value, xos_u64 deadline)
{ (void) address; (void) value; now = deadline; return -13; }
long __xos_wake_word (xos_u32 *address, xos_u32 count)
{ (void) address; (void) count; return 0; }
long __xos_file_lease_acquire (int fd, int access, struct xos_file_lease *lease)
{
  (void) access;
  if (fd != 3 && fd != 4 && fd != 5 && fd != 10 && fd != 1) return -EBADF;
  *lease = (struct xos_file_lease) { .object = fd, .kind = fd == 10 ? xos_file_kind_file
    : fd == 1 ? xos_file_kind_kernel : xos_file_kind_socket, .handle = route_for_fd[fd], .flags = nonblocking ? O_NONBLOCK : 0 };
  ++leases; return 0;
}
long __xos_file_lease_release (struct xos_file_lease *lease)
{ assert (leases && lease->object >= 0); --leases; lease->object = -1; return 0; }
long __xos_file_poll_lease_acquire (int fd, struct xos_file_lease *lease)
{ return __xos_file_lease_acquire (fd, -1, lease); }
long __xos_file_poll_lease_current (int fd, const struct xos_file_lease *lease)
{
  if (current_busy) { --current_busy; return -EAGAIN; }
  return route_for_fd[fd] == lease->handle ? 0 : -EBADF;
}
void __xos_file_poll_lease_release (struct xos_file_lease *lease)
{ (void) __xos_file_lease_release (lease); }
long __xos_file_test_trap (xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
  if (number == 54) return -18;
  if (number == 46) { publish_page (); return now; }
  if (number == 88)
    {
      if (first == 21) { struct xos_net2_grant_map *map = (void *) second; assert (map->handle == 991 && map->access == 1); map->address = (xos_u64) &shared_page; map->map_id = 3; map->length = 4096; return 0; }
      if (first == 24) { ++release_attempts; return release_error; }
    }
  if (number == 47)
    {
      assert (first > now); now = first;
      if (move_fd_on_sleep) { route_for_fd[3] = route_for_fd[5]; move_fd_on_sleep = 0; }
      return 0;
    }
  if (number == 86) { ++name_connections; xos_u32 *pair = (xos_u32 *) third; pair[0] = 11; pair[1] = 12; return 0; }
  if (number == 85)
    {
      assert (second == 5 || second == 6);
      if (legacy_kernel) return -2;
      if (second == 5 && no_reply) { now = third; return -13; }
      return 0;
    }
  if (number == 84)
    {
      if (first == 2) {
        if (advance_page_on_peer) { advance_page_on_peer = 0; ++now; publish_page (); }
        *(xos_u64 *) third = 42; return 0;
      }
      if (first == 3) { ++closes; return 0; }
    }
  if (number == 4)
    {
      assert (first == 11 && third <= sizeof (request));
      memcpy (&request, (const void *) second, third);
      assert (request.action < 21); ++calls[request.action]; return 0;
    }
  if (number == 5)
    {
      assert (first == 12 && third == sizeof (request));
      if (no_reply) return -3;
      struct xos_net2_message *reply = (void *) second;
      *reply = (struct xos_net2_message) { .version = 2, .action = request.action,
        .sequence = request.sequence, .object = request.object };
      if (request.action == xos_net2_open) { reply->object = next_handle++; reply->flags = pending_connect ? xos_net2_connecting : xos_net2_connected; }
      else if (request.action == xos_net2_capabilities)
        {
          if (old_server) reply->result = xos_net2_unsupported;
          else
            {
              const struct xos_net2_capability_snapshot snapshot = { request.flags ? 2 : 1, page_mode && request.flags ? 15 : 3, 0 };
              memcpy (reply->data, &snapshot, sizeof (snapshot)); reply->length = sizeof (snapshot);
            }
        }
      else if (request.action == xos_net2_readiness)
        {
          last_handle = request.object;
          if (move_fd_on_reply) { route_for_fd[3] = route_for_fd[5]; move_fd_on_reply = 0; }
          if (busy_after_reply) { current_busy = busy_after_reply; busy_after_reply = 0; }
          struct xos_net2_readiness_snapshot snapshot = model_readiness ();
          snapshot.events &= 63;
          memcpy (reply->data, &snapshot, sizeof (snapshot)); reply->length = sizeof (snapshot);
        }
      else if (request.action == xos_net2_readiness_bind)
        {
          assert (page_mode);
          const struct xos_net2_readiness_binding binding = { 1, 4096, 991, 13, 0 };
          memcpy (reply->data, &binding, sizeof (binding)); reply->length = sizeof (binding);
        }
      else if (request.action == xos_net2_shutdown_read) closed_read = 1;
      else if (request.action == xos_net2_shutdown_write) closed_write = 1;
      else if (request.action == xos_net2_send) reply->result = request.length;
      return 64 + reply->length;
    }
  assert (!"unexpected trap"); return -1;
}
static void reset_fixture (void)
{
  __xos_net2_after_fork (); memset (calls, 0, sizeof (calls));
  now = 100000000; next_handle = 17; ready_after = 0; leases = closes = 0;
  old_server = malformed = move_fd_on_sleep = no_reply = legacy_kernel = 0;
  page_mode = freeze_page = nonblocking = pending_connect = closed_read = closed_write = 0;
  release_error = move_fd_on_reply = current_busy = busy_after_reply = 0;
  release_attempts = name_connections = 0;
  shared_page = (struct xos_net2_readiness_page) { 0 };
  route_for_fd[3] = route_for_fd[4] = __xos_net2_alloc ();
  route_for_fd[5] = __xos_net2_alloc ();
}
int main (void)
{
  assert (setenv ("XOS_NET_SERVICE_PID", "42", 1) == 0); reset_fixture ();
  struct pollfd item = { .fd = 3, .events = POLLIN };
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == POLLHUP && !leases);
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  item.events = POLLOUT;
  assert (__xos_net2_poll (&item, 1, 0) == -EOPNOTSUPP && !leases);
  assert (__xos_net2_poll (&item, 1, 5) == 1 && item.revents == POLLOUT && !leases);
  item.events = POLLIN;
  assert (__xos_net2_poll (&item, 1, 2) == 0 && !item.revents);
  xos_u64 began = now;
  assert (__xos_net2_poll (&item, 1, 20) == 0 && now == began + 20000000 && !leases);
  assert (calls[xos_net2_capabilities] == 1);
  ready_after = now + 5000000;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLIN && now == ready_after);
  assert (__xos_net2_shutdown_fd (4, SHUT_WR) == 0 && __xos_net2_shutdown_fd (3, SHUT_WR) == 0);
  assert (calls[xos_net2_shutdown_write] == 1);
  assert (__xos_net2_stream_fd (3, (void *) "x", 1, 1) == -EPIPE && !leases);
  assert (__xos_net2_shutdown_fd (3, SHUT_RD) == -EOPNOTSUPP);
  assert (__xos_net2_poll (NULL, 1, 0) == -EFAULT);
  assert (__xos_net2_poll (&item, 33, 0) == -EINVAL);
  item.fd = 10; item.events = POLLIN | POLLOUT;
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == (POLLIN | POLLOUT));
  item.fd = 1;
  assert (__xos_net2_poll (&item, 1, 0) == -EOPNOTSUPP && !leases);
  item.fd = 99;
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == POLLNVAL);

  reset_fixture (); legacy_kernel = 1;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  item = (struct pollfd) { .fd = 3, .events = POLLIN };
  assert (__xos_net2_poll (&item, 1, 20) == -EOPNOTSUPP && !leases && !closes);
  assert (__xos_net2_shutdown_fd (3, SHUT_WR) == -EOPNOTSUPP && !calls[xos_net2_capabilities]);
  assert (__xos_net2_stream_fd (3, (void *) "x", 1, 1) == 1);

  reset_fixture (); old_server = 1;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  item = (struct pollfd) { .fd = 3, .events = POLLIN };
  assert (__xos_net2_poll (&item, 1, 5) == -EOPNOTSUPP && !leases);
  assert (__xos_net2_shutdown_fd (3, SHUT_WR) == -EOPNOTSUPP);
  assert (__xos_net2_stream_fd (3, (void *) "x", 1, 1) == 1 && !closes);

  reset_fixture ();
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  assert (__xos_net2_connect_fd (5, 0x0a000202, 9) == 0);
  ready_after = now + 3000000; move_fd_on_sleep = 1;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLNVAL && last_handle == 17 && !leases);
  assert (route_for_fd[3] == route_for_fd[5]); // In-flight description stayed on the old connection.
  malformed = 1;
  assert (__xos_net2_poll (&item, 1, 5) == -EIO && closes == 2 && !leases);
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == (POLLERR | POLLHUP));
  reset_fixture ();
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  no_reply = 1; began = now;
  item = (struct pollfd) { .fd = 3, .events = POLLOUT };
  assert (__xos_net2_poll (&item, 1, 20) == 0 && now == began + 20000000 && !closes && !leases);
  assert (calls[xos_net2_capabilities] == 1);
  struct pollfd mixed[2] = { { .fd = 3, .events = POLLOUT }, { .fd = 99, .events = POLLIN } };
  began = now;
  assert (__xos_net2_poll (mixed, 2, 20) == 1 && mixed[1].revents == POLLNVAL && !leases && now == began);
  mixed[1].fd = 10;
  assert (__xos_net2_poll (mixed, 2, 20) == 1 && mixed[1].revents == POLLIN && now == began);
  no_reply = 0;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLOUT && !closes);
  assert (calls[xos_net2_capabilities] == 1); // Capability negotiated only once.
  no_reply = 1; began = now;
  assert (__xos_net2_poll (&item, 1, 20) == 0 && now == began + 20000000 && !closes);
  unsigned int queries = calls[xos_net2_readiness]; no_reply = 0;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && calls[xos_net2_readiness] == queries && !leases);
  reset_fixture ();
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  assert (__xos_net2_connect_fd (5, 0x0a000202, 9) == 0);
  move_fd_on_reply = 1; ready_after = now;
  item = (struct pollfd) { .fd = 3, .events = POLLIN };
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLNVAL && last_handle == 17 && !leases);
  reset_fixture ();
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  assert (__xos_net2_connect_fd (5, 0x0a000202, 9) == 0);
  current_busy = 2; move_fd_on_sleep = 1;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLNVAL && !leases);
  reset_fixture ();
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  assert (__xos_net2_connect_fd (5, 0x0a000202, 9) == 0);
  move_fd_on_reply = 1; busy_after_reply = 1; ready_after = now;
  assert (__xos_net2_poll (&item, 1, 20) == 1 && item.revents == POLLNVAL && !leases);
  reset_fixture (); page_mode = 1;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  item = (struct pollfd) { .fd = 3, .events = POLLOUT };
  current_busy = 1;
  assert (__xos_net2_poll (&item, 1, 0) == -EAGAIN && !item.revents && !leases);
  current_busy = 100; began = now;
  assert (__xos_net2_poll (&item, 1, 20) == 0 && !item.revents && now == began + 20000000 && !leases);
  current_busy = 0;
  began = now;
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == POLLOUT && now == began);
  item.events = POLLIN; freeze_page = 1; now += 100;
  assert (__xos_net2_poll (&item, 1, 0) == -EAGAIN && !item.revents && !leases);
  freeze_page = 0;
  assert (__xos_net2_poll (&item, 1, 0) == -EAGAIN && !item.revents);
  advance_page_on_peer = 1;
  assert (__xos_net2_poll (&item, 1, 0) == 0 && !item.revents);
  shared_page.sequence |= 1; freeze_page = 1;
  assert (__xos_net2_poll (&item, 1, 0) == -EAGAIN && !item.revents);
  freeze_page = 0; shared_page.sequence = 2;
  assert (__xos_net2_shutdown_fd (3, SHUT_RD) == 0);
  assert (__xos_net2_stream_fd (3, &malformed, 1, 0) == 0);
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == (POLLIN | POLLHUP));
  assert (__xos_net2_shutdown_fd (3, SHUT_RDWR) == 0);
  assert (__xos_net2_stream_fd (3, &malformed, 1, 1) == -EPIPE);
  reset_fixture (); page_mode = nonblocking = pending_connect = 1;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == -EINPROGRESS);
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == -EALREADY);
  pending_connect = 0; item.events = POLLOUT;
  assert (__xos_net2_poll (&item, 1, 0) == 1 && item.revents == POLLOUT);
  int socket_error = -1;
  assert (__xos_net2_error_fd (3, &socket_error) == 0 && socket_error == 0);
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == -EISCONN);
  reset_fixture (); page_mode = 1;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0);
  release_error = -107;
  __xos_net2_retire (route_for_fd[3]); __xos_net2_reap ();
  assert (release_attempts == 1);
  route_for_fd[3] = __xos_net2_alloc ();
  unsigned int before_connections = name_connections;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == -EAGAIN && name_connections == before_connections);
  release_error = 0;
  assert (__xos_net2_connect_fd (3, 0x0a000202, 9) == 0 && release_attempts == 3);
  __xos_net2_retire (route_for_fd[3]); __xos_net2_reap ();
  puts ("PASS actual glibc Net2 bridge: level polling, absolute timeout, FD leases, half-close, old server, malformed reply");
  return 0;
}
