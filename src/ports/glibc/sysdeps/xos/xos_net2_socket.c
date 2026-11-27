/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include "xos_file_runtime.h"
#include "xos_file_trap.h"
#include "xos_net2_socket.h"
#include "xos_net2_wire.h"

_Static_assert (sizeof (struct xos_net2_message) == 1088, "Net2 wire size");
_Static_assert (offsetof (struct xos_net2_message, data) == 64, "Net2 wire header");
_Static_assert (sizeof (struct xos_net2_capability_snapshot) == 16, "Net2 capability layout");
_Static_assert (sizeof (struct xos_net2_readiness_snapshot) == 32, "Net2 readiness layout");

struct socket_route
{
  xos_u32 allocated, write_closed, ready_valid;
  xos_u64 generation, handle;
  long ready_result;
  struct xos_net2_readiness_snapshot ready;
};
struct ipc_pair { xos_u32 send, receive; };
static struct socket_route routes[xos_net2_local_sockets];
static struct ipc_pair channel;
static xos_u32 net_lock, retired;
static xos_u32 capability_flags, capabilities_known;
static long capability_error;
static int deadline_modes_known;
/* Only read-only queries may outlive poll's deadline. No application buffer,
   descriptor number or side-effecting request is retained here. */
static struct xos_net2_message pending_query;
static xos_u64 pending_generation;
static unsigned int pending_slot;
static int query_pending;
static xos_u64 generation, sequence;
static const xos_u64 request_limit = 30000000000ULL, tick = 1000000ULL;
enum { ipc_send = 4, ipc_receive = 5, monotonic = 46, sleep_until = 47,
       ipc_endpoint = 84, ipc_name = 86, name_connect = 2, endpoint_peer = 2,
       endpoint_close = 3, ipc_empty = -3, ipc_full = -4, wait_timeout = -13,
       wait_changed = -14 };

static xos_u64
deadline_now (void)
{
  long now = file_trap (monotonic, 0, 0, 0);
  return now < 0 || (xos_u64) now > LONG_MAX - request_limit ? 0
    : (xos_u64) now + request_limit;
}

static int
lock_net (xos_u64 deadline)
{
  while (__atomic_exchange_n (&net_lock, 1, __ATOMIC_ACQUIRE) != 0)
    {
      long result = __xos_wait_word (&net_lock, 1, deadline);
      if (result != 0 && result != wait_changed)
        return result == wait_timeout ? -ETIMEDOUT : -EIO;
    }
  return 0;
}

static void
unlock_net (void)
{
  __atomic_store_n (&net_lock, 0, __ATOMIC_RELEASE);
  (void) __xos_wake_word (&net_lock, 1);
}

static int
pause_until (xos_u64 deadline)
{
  long current = file_trap (monotonic, 0, 0, 0);
  if (current < 0) return -EIO;
  xos_u64 now = (xos_u64) current;
  if (now >= deadline) return -ETIMEDOUT;
  const xos_u64 next = deadline - now < tick ? deadline : now + tick;
  return file_trap (sleep_until, next, 0, 0) == 0 ? 0 : -EIO;
}

static void
drop_session (void)
{
  if (channel.send) (void) file_trap (ipc_endpoint, endpoint_close, channel.send, 0);
  if (channel.receive) (void) file_trap (ipc_endpoint, endpoint_close, channel.receive, 0);
  channel = (struct ipc_pair) { 0 };
  sequence = 0;
  capability_flags = capabilities_known = 0; capability_error = 0; query_pending = 0; deadline_modes_known = 0;
}

static int
open_session (void)
{
  if (channel.send) return 0;
  const char *value = getenv ("XOS_NET_SERVICE_PID");
  if (!value || !*value) return -ENETDOWN;
  xos_u64 expected = 0, send_peer = 0, receive_peer = 0;
  for (; *value; ++value)
    {
      unsigned int digit = (unsigned int) ((unsigned char) *value - '0');
      if (digit > 9 || expected > (~(xos_u64) 0 - digit) / 10) return -EACCES;
      expected = expected * 10 + digit;
    }
  if (!expected) return -EACCES;
  if (generation == ~(xos_u64) 0) return -EOVERFLOW;
  if (file_trap (ipc_name, name_connect, (xos_u64) "net2", (xos_u64) &channel) != 0)
    {
      drop_session ();
      return -ENETDOWN;
    }
  if (file_trap (ipc_endpoint, endpoint_peer, channel.send, (xos_u64) &send_peer) != 0
      || file_trap (ipc_endpoint, endpoint_peer, channel.receive, (xos_u64) &receive_peer) != 0
      || send_peer != expected || receive_peer != expected)
    {
      drop_session ();
      return -EACCES;
    }
  ++generation;
  sequence = 1;
  return 0;
}

static int
network_error (long value)
{
  switch (value)
    {
    case xos_net2_invalid: return -EINVAL;
    case xos_net2_denied: return -EACCES;
    case xos_net2_resources: return -ENOBUFS;
    case xos_net2_again: return -EAGAIN;
    case xos_net2_timeout: return -ETIMEDOUT;
    case xos_net2_closed: return -ENOTCONN;
    case xos_net2_unsupported: return -EOPNOTSUPP;
    case xos_net2_reset: return -ECONNRESET;
    default: return -EIO;
    }
}

static int
valid_response (const struct xos_net2_message *request, const struct xos_net2_message *reply, long bytes)
{
  const int opening = request->action == xos_net2_open;
  if (bytes < xos_net2_header_bytes || reply->version != xos_net2_version
      || reply->action != request->action || reply->sequence != request->sequence
      || reply->deadline || reply->reserved || reply->address || reply->port || reply->transport
      || reply->length > xos_net2_payload_bytes || bytes != xos_net2_header_bytes + reply->length
      || (opening ? ((reply->result == 0) != (reply->object != 0)) : reply->object != request->object))
    return 0;
  if (reply->result < 0)
    return reply->result >= xos_net2_reset && reply->result <= xos_net2_invalid
      && reply->length == 0 && (reply->flags == 0
          || ((opening || request->action == xos_net2_status) && reply->flags == xos_net2_failed));
  switch (request->action)
    {
    case xos_net2_open: case xos_net2_status:
      return reply->result == 0 && reply->length == 0
        && (reply->flags == xos_net2_connecting || reply->flags == xos_net2_connected
            || reply->flags == (xos_net2_connected | xos_net2_eof));
    case xos_net2_send:
      return reply->length == 0 && reply->flags == 0 && reply->result > 0
        && (xos_u64) reply->result <= request->length;
    case xos_net2_receive:
      return reply->result == 0 && reply->length <= request->flags
        && !(reply->flags & ~(xos_u32) xos_net2_eof) && (reply->length != 0 || reply->flags == xos_net2_eof);
    case xos_net2_capabilities:
      {
        struct xos_net2_capability_snapshot snapshot;
        if (reply->result || reply->flags || reply->length != sizeof (snapshot)) return 0;
        memcpy (&snapshot, reply->data, sizeof (snapshot));
        return snapshot.revision == xos_net2_extension_revision && !snapshot.reserved
          && !(snapshot.flags & ~(xos_u32) (xos_net2_cap_readiness | xos_net2_cap_shutdown_write));
      }
    case xos_net2_readiness:
      {
        struct xos_net2_readiness_snapshot snapshot;
        if (reply->result || reply->flags || reply->length != sizeof (snapshot)) return 0;
        memcpy (&snapshot, reply->data, sizeof (snapshot));
        return snapshot.generation && !snapshot.reserved && !(snapshot.events & ~63U)
          && snapshot.readable_bytes <= 8192
          && ((snapshot.error < 0 && snapshot.error >= xos_net2_reset && snapshot.error <= xos_net2_invalid
               && (snapshot.events & xos_net2_ready_error))
              || (!snapshot.error && !(snapshot.events & xos_net2_ready_error)))
          && (!snapshot.readable_bytes || (snapshot.events & xos_net2_ready_read))
          && ((snapshot.writable_bytes != 0) == ((snapshot.events & xos_net2_ready_write) != 0))
          && (!(snapshot.events & xos_net2_ready_eof)
              || ((snapshot.events & xos_net2_ready_read) && !snapshot.error))
          && (!(snapshot.events & xos_net2_ready_write_closed) || !(snapshot.events & xos_net2_ready_write));
      }
    default:
      return reply->result == 0 && reply->length == 0 && reply->flags == 0;
    }
}

/* Await a transport event only until the supplied absolute deadline. The
   timed profile requires modes 5/6; an older kernel fails closed. */
static long
wait_channel (xos_u32 endpoint, xos_u32 mode, xos_u64 deadline)
{
  long waited = file_trap (85, endpoint, mode, deadline);
  if (waited == 0) return 0;
  if (waited == wait_timeout) return -EAGAIN;
  return waited == -2 ? -EOPNOTSUPP : -ENETDOWN;
}

/* Caller holds net_lock. A user poll timeout keeps this read-only exchange
   alive; a transport deadline, broken channel or bad response retires it. */
static long
finish_query (xos_u64 deadline)
{
  while (query_pending)
    {
      long clock = file_trap (monotonic, 0, 0, 0);
      if (clock < 0) { drop_session (); return -EIO; }
      if ((xos_u64) clock >= pending_query.deadline)
        { drop_session (); return -ETIMEDOUT; }
      struct xos_net2_message reply;
      long received = file_trap (ipc_receive, channel.receive, (xos_u64) &reply, sizeof (reply));
      if (received == ipc_empty)
        {
          if ((xos_u64) clock >= deadline) return -EAGAIN;
          xos_u64 limit = deadline < pending_query.deadline ? deadline : pending_query.deadline;
          long waited = wait_channel (channel.receive, 5, limit);
          if (waited == -EAGAIN) return -EAGAIN;
          if (waited) { drop_session (); return waited; }
          continue;
        }
      clock = file_trap (monotonic, 0, 0, 0);
      if (clock < 0 || (xos_u64) clock >= pending_query.deadline)
        { drop_session (); return clock < 0 ? -EIO : -ETIMEDOUT; }
      if (received < 0 || !valid_response (&pending_query, &reply, received))
        { drop_session (); return received < 0 ? -ENETDOWN : -EIO; }
      if (pending_generation != generation) { drop_session (); return -EIO; }
      if (pending_query.action == xos_net2_capabilities)
        {
          capabilities_known = 1;
          capability_error = reply.result < 0 ? network_error (reply.result) : 0;
          capability_flags = 0;
          if (!capability_error)
            {
              struct xos_net2_capability_snapshot snapshot;
              memcpy (&snapshot, reply.data, sizeof (snapshot)); capability_flags = snapshot.flags;
            }
        }
      else
        {
          struct socket_route *route = &routes[pending_slot];
          if (route->generation == pending_generation && route->handle == pending_query.object)
            {
              route->ready_result = reply.result < 0 ? network_error (reply.result) : 0;
              if (!route->ready_result) memcpy (&route->ready, reply.data, sizeof (route->ready));
              route->ready_valid = 1;
            }
        }
      query_pending = 0;
      /* A late, valid reply is consumed once but cannot extend this poll. */
      clock = file_trap (monotonic, 0, 0, 0);
      if (clock < 0) { drop_session (); return -EIO; }
      if ((xos_u64) clock >= deadline) return -EAGAIN;
    }
  return 0;
}

static long
start_query (xos_u32 action, unsigned int slot, xos_u64 object, xos_u64 deadline)
{
  long result = finish_query (deadline);
  if (result) return result;
  if (!channel.send || !sequence) return -ENETDOWN;
  const xos_u64 transport_deadline = deadline_now ();
  if (!transport_deadline) return -EIO;
  pending_query = (struct xos_net2_message) { .version = xos_net2_version,
    .action = action, .object = object, .sequence = sequence, .deadline = transport_deadline };
  for (;;)
    {
      long now = file_trap (monotonic, 0, 0, 0);
      if (now < 0) { drop_session (); return -EIO; }
      if ((xos_u64) now >= deadline) return -EAGAIN;
      if ((xos_u64) now >= transport_deadline) return -ETIMEDOUT;
      long sent = file_trap (ipc_send, channel.send, (xos_u64) &pending_query, xos_net2_header_bytes);
      if (sent == 0)
        {
          ++sequence; query_pending = 1; pending_slot = slot; pending_generation = generation;
          return finish_query (deadline);
        }
      if (sent != ipc_full) { drop_session (); return -ENETDOWN; }
      result = wait_channel (channel.send, 6, deadline < transport_deadline ? deadline : transport_deadline);
      if (result) return result;
    }
}

/* net_lock serializes a single request/reply. The service owns accepted bytes
   even if the client loses the response. Such a request is never replayed. */
static long
exchange (struct xos_net2_message *request, struct xos_net2_message *reply, xos_u64 deadline)
{
  long failure = finish_query (deadline);
  if (failure) return failure == -EAGAIN ? -ETIMEDOUT : failure;
  failure = -EIO;
  for (unsigned int slot = 0; slot < xos_net2_local_sockets; ++slot) routes[slot].ready_valid = 0;
  if (!channel.send || !sequence) return -ENETDOWN;
  request->version = xos_net2_version;
  request->deadline = deadline;
  request->sequence = sequence;
  int sent = 0;
  for (;;)
    {
      long now = file_trap (monotonic, 0, 0, 0);
      if (now < 0) break;
      if ((xos_u64) now >= deadline) { failure = -ETIMEDOUT; break; }
      if (!sent)
        {
          long result = file_trap (ipc_send, channel.send, (xos_u64) request,
                                   xos_net2_header_bytes + request->length);
          if (result == 0) { sent = 1; ++sequence; }
          else if (result != ipc_full) { failure = -ENETDOWN; break; }
        }
      if (sent)
        {
          long result = file_trap (ipc_receive, channel.receive, (xos_u64) reply, sizeof (*reply));
          if (result != ipc_empty)
            {
              long finish = file_trap (monotonic, 0, 0, 0);
              if (finish < 0) break;
              if ((xos_u64) finish >= deadline) { failure = -ETIMEDOUT; break; }
              if (result < 0) { failure = -ENETDOWN; break; }
              if (!valid_response (request, reply, result)) break;
              return reply->result < 0 ? network_error (reply->result) : reply->result;
            }
        }
      failure = pause_until (deadline);
      if (failure) break;
      failure = -EIO;
    }
  if (sent || failure != -ETIMEDOUT) drop_session ();
  return failure;
}

static int
current_route (const struct socket_route *route)
{
  return channel.send && route->handle && route->generation == generation;
}

static void
release_route (struct socket_route *route, xos_u64 deadline, int cancelling)
{
  if (current_route (route))
    {
      struct xos_net2_message reply, request = {
        .action = cancelling ? xos_net2_cancel : xos_net2_close, .object = route->handle };
      long result = exchange (&request, &reply, deadline);
      if (result == -EAGAIN && !cancelling)
        {
          request = (struct xos_net2_message) { .action = xos_net2_cancel, .object = route->handle };
          result = exchange (&request, &reply, deadline);
        }
      if (result < 0 && result != -ENOTCONN) drop_session ();
    }
  route->handle = route->generation = 0;
  route->write_closed = route->ready_valid = 0;
}

long
__xos_net2_alloc (void)
{
  for (unsigned int slot = 0; slot < xos_net2_local_sockets; ++slot)
    {
      xos_u32 unallocated = 0;
      if (__atomic_compare_exchange_n (&routes[slot].allocated, &unallocated, 1, 0,
                                      __ATOMIC_ACQ_REL, __ATOMIC_RELAXED))
        return slot;
    }
  return -EMFILE;
}

void
__xos_net2_retire (unsigned int slot)
{
  __atomic_fetch_or (&retired, (xos_u32) 1 << slot, __ATOMIC_RELEASE);
}

void
__xos_net2_reap (void)
{
  if (!__atomic_load_n (&retired, __ATOMIC_ACQUIRE)) return;
  xos_u64 deadline = deadline_now ();
  if (!deadline || lock_net (deadline) != 0) return;
  xos_u32 batch = __atomic_exchange_n (&retired, 0, __ATOMIC_ACQUIRE);
  while (batch)
    {
      unsigned int slot = (unsigned int) __builtin_ctz (batch);
      batch &= batch - 1;
      release_route (&routes[slot], deadline, 0);
      __atomic_store_n (&routes[slot].allocated, 0, __ATOMIC_RELEASE);
    }
  for (unsigned int slot = 0; slot < xos_net2_local_sockets; ++slot)
    if (current_route (&routes[slot])) { unlock_net (); return; }
  drop_session ();
  unlock_net ();
}

void
__xos_net2_after_fork (void)
{
  channel = (struct ipc_pair) { 0 };
  generation = sequence = retired = net_lock = 0;
  capability_flags = capabilities_known = 0; capability_error = 0; query_pending = 0; deadline_modes_known = 0;
  memset (routes, 0, sizeof (routes));
}

static long
connect_route (unsigned int slot, xos_u32 address, unsigned int port)
{
  const xos_u64 deadline = deadline_now ();
  if (!deadline) return -EIO;
  long result = lock_net (deadline);
  if (result) return result;
  struct socket_route *route = &routes[slot];
  if (current_route (route)) { result = -EISCONN; goto done; }
  if (route->handle) { result = -ENETDOWN; goto done; }
  result = open_session ();
  if (result) goto done;
  struct xos_net2_message reply, request = {
    .action = xos_net2_open, .transport = xos_net2_tcp, .address = address, .port = (__UINT16_TYPE__) port };
  result = exchange (&request, &reply, deadline);
  if (result == 0)
    {
      route->generation = generation;
      route->handle = reply.object;
      while (result == 0 && reply.flags == xos_net2_connecting)
        {
          result = pause_until (deadline);
          if (result != 0) break;
          request = (struct xos_net2_message) { .action = xos_net2_status, .object = route->handle };
          result = exchange (&request, &reply, deadline);
        }
      if (result) release_route (route, deadline, 1);
    }
  if (result == -ECONNRESET) result = -ECONNREFUSED;
done:
  unlock_net ();
  return result;
}

long
__xos_net2_stream (unsigned int slot, void *buffer, size_t size, int writing)
{
  if (!buffer && size) return -EFAULT;
  const xos_u64 deadline = deadline_now ();
  if (!deadline) return -EIO;
  const xos_u32 count = size <= xos_net2_payload_bytes ? (xos_u32) size : xos_net2_payload_bytes;
  for (;;)
    {
      long result = lock_net (deadline);
      if (result) return result;
      const struct socket_route *route = &routes[slot];
      if (!current_route (route)) result = route->handle ? -ENETDOWN : -ENOTCONN;
      else if (writing && route->write_closed) result = -EPIPE;
      else if (count)
        {
          struct xos_net2_message reply, request = {
            .action = writing ? xos_net2_send : xos_net2_receive, .object = route->handle };
          if (writing) { request.length = count; memcpy (request.data, buffer, count); }
          else request.flags = count;
          result = exchange (&request, &reply, deadline);
          if (result == 0 && !writing)
            { memcpy (buffer, reply.data, reply.length); result = reply.length; }
        }
      unlock_net ();
      if (result != -EAGAIN) return result;
      result = pause_until (deadline);
      if (result) return result;
    }
}

long
__xos_net2_connect_fd (int fd, xos_u32 address, unsigned int port)
{
  struct xos_file_lease lease;
  long result = __xos_file_lease_acquire (fd, -1, &lease);
  if (result < 0) return result;
  result = lease.kind == xos_file_kind_socket
    ? connect_route (lease.handle, address, port) : -ENOTSOCK;
  (void) __xos_file_lease_release (&lease);
  return result;
}

long
__xos_net2_stream_fd (int fd, void *buffer, size_t size, int writing)
{
  struct xos_file_lease lease;
  long result = __xos_file_lease_acquire (fd, -1, &lease);
  if (result < 0) return result;
  result = lease.kind == xos_file_kind_socket
    ? __xos_net2_stream (lease.handle, buffer, size, writing) : -ENOTSOCK;
  (void) __xos_file_lease_release (&lease);
  return result;
}

static long
require_deadline_modes (void)
{
  if (deadline_modes_known) return 0;
  const long now = file_trap (monotonic, 0, 0, 0);
  if (now < 0) return -EIO;
  /* Non-consuming probes at an already reached deadline never wait. This
     rejects an older kernel before a new service operation can be submitted. */
  for (unsigned int sending = 0; sending < 2; ++sending)
    {
      long result = file_trap (85, sending ? channel.send : channel.receive,
                               sending ? 6 : 5, (xos_u64) now);
      if (result != 0 && result != wait_timeout)
        return result == -2 ? -EOPNOTSUPP : -ENETDOWN;
    }
  deadline_modes_known = 1;
  return 0;
}

/* Caller holds net_lock; capability support is scoped to this authenticated
   channel generation. Unsupported probes never fall back to invented flags. */
static long
require_capability (xos_u32 flag, xos_u64 deadline)
{
  long supported = require_deadline_modes ();
  if (supported) return supported;
  if (!capabilities_known)
    {
      long result = finish_query (deadline);
      if (result) return result;
      if (!capabilities_known)
        {
          result = start_query (xos_net2_capabilities, 0, 0, deadline);
          if (result) return result;
        }
    }
  return capability_error ? capability_error : capability_flags & flag ? 0 : -EOPNOTSUPP;
}

long
__xos_net2_shutdown_fd (int fd, int how)
{
  if (how != SHUT_WR) return how == SHUT_RD || how == SHUT_RDWR ? -EOPNOTSUPP : -EINVAL;
  struct xos_file_lease lease;
  long result = __xos_file_lease_acquire (fd, -1, &lease);
  if (result < 0) return result;
  if (lease.kind != xos_file_kind_socket) result = -ENOTSOCK;
  else
    {
      const xos_u64 deadline = deadline_now ();
      result = deadline ? lock_net (deadline) : -EIO;
      if (result == 0)
        {
          struct socket_route *route = &routes[lease.handle];
          if (!current_route (route)) result = route->handle ? -ENETDOWN : -ENOTCONN;
          else if (!route->write_closed)
            {
              result = require_capability (xos_net2_cap_shutdown_write, deadline);
              if (result == 0)
                {
                  struct xos_net2_message reply, request = {
                    .action = xos_net2_shutdown_write, .object = route->handle };
                  result = exchange (&request, &reply, deadline);
                  if (result == 0) route->write_closed = 1;
                }
            }
          unlock_net ();
        }
    }
  (void) __xos_file_lease_release (&lease);
  return result == -EAGAIN ? -ETIMEDOUT : result;
}

static long
poll_route (unsigned int slot, short events, short *revents, xos_u64 deadline, int immediate)
{
  long result = 0;
  if (immediate)
    {
      if (__atomic_exchange_n (&net_lock, 1, __ATOMIC_ACQUIRE) != 0) return -EOPNOTSUPP;
    }
  else result = lock_net (deadline);
  if (result) return result == -ETIMEDOUT ? -EAGAIN : result;
  struct socket_route *route = &routes[slot];
  if (!route->handle) { *revents = POLLHUP; result = 0; }
  else if (!current_route (route)) { *revents = POLLERR | POLLHUP; result = 0; }
  else if (immediate) result = -EOPNOTSUPP;
  else
    {
      result = require_capability (xos_net2_cap_readiness, deadline);
      if (result == 0) result = finish_query (deadline);
      if (result == 0 && !route->ready_valid)
        result = start_query (xos_net2_readiness, slot, route->handle, deadline);
      if (result == 0)
        {
          result = route->ready_result;
          if (!route->ready_valid) result = -EIO;
          else if (result == 0)
            {
              const struct xos_net2_readiness_snapshot *snapshot = &route->ready;
              if ((events & POLLIN) && (snapshot->events & xos_net2_ready_read)) *revents |= POLLIN;
              if ((events & POLLOUT) && (snapshot->events & xos_net2_ready_write)) *revents |= POLLOUT;
              if (snapshot->events & xos_net2_ready_eof) *revents |= POLLHUP;
              if (snapshot->events & xos_net2_ready_error) *revents |= POLLERR;
            }
          route->ready_valid = 0;
        }
    }
  unlock_net ();
  return result;
}

long
__xos_net2_poll (struct pollfd *descriptors, nfds_t count, int timeout_ms)
{
  /* The FD table has 32 entries. Holding descriptions for the whole wait
     prevents concurrent close/reuse from redirecting an in-flight poll. */
  if (count > xos_net2_local_sockets) return -EINVAL;
  if (!descriptors && count) return -EFAULT;
  struct xos_file_lease leases[xos_net2_local_sockets];
  long result = 0;
  for (nfds_t i = 0; i < count; ++i)
    { leases[i].object = -1; descriptors[i].revents = 0; }
  const long began = file_trap (monotonic, 0, 0, 0);
  if (began < 0) return -EIO;
  const xos_u64 until = timeout_ms < 0 ? 0 : (xos_u64) began + (xos_u64) (unsigned int) timeout_ms * (xos_u64) 1000000;
  for (nfds_t i = 0; i < count; ++i)
    {
      descriptors[i].revents = 0;
      if (descriptors[i].fd < 0) continue;
      if (descriptors[i].events & ~(POLLIN | POLLOUT | POLLERR | POLLHUP | POLLNVAL))
        { result = -EOPNOTSUPP; goto done; }
      long acquired;
      for (;;)
        {
          acquired = __xos_file_poll_lease_acquire (descriptors[i].fd, &leases[i]);
          if (acquired != -EAGAIN) break;
          if (timeout_ms == 0) { result = -EOPNOTSUPP; goto done; }
          long paused = pause_until (until ? until : deadline_now ());
          if (paused)
            {
              result = paused == -ETIMEDOUT ? 0 : paused;
              if (!result)
                for (nfds_t ready = 0; ready < count; ++ready)
                  if (descriptors[ready].revents) ++result;
              goto done;
            }
        }
      if (acquired == -EBADF) { descriptors[i].revents = POLLNVAL; continue; }
      if (acquired) { result = acquired; goto done; }
      if (leases[i].kind != xos_file_kind_socket && leases[i].kind != xos_file_kind_file)
        { result = -EOPNOTSUPP; goto done; }
    }
  for (;;)
    {
      long ready_count = 0;
      /* One caller deadline covers lock acquisition, capability negotiation,
         snapshots and waiting. A read-only RPC may be consumed by a later call. */
      const xos_u64 query_deadline = until ? until : deadline_now ();
      if (!query_deadline) { result = -EIO; break; }
      for (nfds_t i = 0; i < count; ++i)
        {
          if (leases[i].object >= 0)
            {
              descriptors[i].revents = 0;
              if (leases[i].kind == xos_file_kind_file)
                descriptors[i].revents = descriptors[i].events & (POLLIN | POLLOUT);
              else
                {
                  result = poll_route (leases[i].handle, descriptors[i].events,
                                       &descriptors[i].revents, query_deadline, timeout_ms == 0);
                  if (result == -EAGAIN)
                    {
                      result = 0;
                      for (nfds_t ready = 0; ready < count; ++ready)
                        if (descriptors[ready].revents) ++result;
                      goto done;
                    }
                  if (result) goto done;
                }
            }
          if (descriptors[i].revents) ++ready_count;
        }
      if (ready_count || timeout_ms == 0) { result = ready_count; break; }
      const long current = file_trap (monotonic, 0, 0, 0);
      if (current < 0) { result = -EIO; break; }
      const xos_u64 now = (xos_u64) current;
      if (until && now >= until) { result = 0; break; }
      xos_u64 next = now > LONG_MAX - tick ? LONG_MAX : now + tick;
      if (until && next > until) next = until;
      if (file_trap (sleep_until, next, 0, 0) != 0) { result = -EIO; break; }
    }
done:
  for (nfds_t i = 0; i < count; ++i)
    if (leases[i].object >= 0) __xos_file_poll_lease_release (&leases[i]);
  return result;
}
