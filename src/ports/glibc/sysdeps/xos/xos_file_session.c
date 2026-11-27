/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <limits.h>
#include "xos_file_session.h"
#include "xos_file_trap.h"

long
__xos_file_service_error (int value)
{
  switch (value)
    {
    case 0: return 0;
    case -1: return -ENOENT;
    case -2: return -EINVAL;
    case -3: return -EMFILE;
    case -4: return -ENOSPC;
    case -5: return -EBUSY;
    case -6: return -EBADF;
    case -7: return -EIO;
    case -8: return -EAGAIN;
    case -9: return -EEXIST;
    case -10: return -ENOTDIR;
    case -11: return -EISDIR;
    case -12: return -ENOTEMPTY;
    case -13: return -ENAMETOOLONG;
    case -14: return -ENOTSUP;
    case -15: return -EROFS;
    case -16: return -EACCES;
    default: return -EIO;
    }
}

static int
valid_text (const unsigned char *data, unsigned int length, int component)
{
  unsigned int at = 0;
  while (at < length)
    {
      unsigned int value = data[at++], continuation = 0, minimum = 0;
      if (value < 0x20 || value == 0x7f || (component && value == '/')) return 0;
      if (value < 0x80) continue;
      if (value >= 0xc2 && value <= 0xdf) { continuation = 1; minimum = 0x80; value &= 31; }
      else if (value >= 0xe0 && value <= 0xef) { continuation = 2; minimum = 0x800; value &= 15; }
      else if (value >= 0xf0 && value <= 0xf4) { continuation = 3; minimum = 0x10000; value &= 7; }
      else return 0;
      if (continuation > length - at) return 0;
      while (continuation-- != 0)
        {
          unsigned int next = data[at++];
          if ((next & 0xc0) != 0x80) return 0;
          value = (value << 6) | (next & 63);
        }
      if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) return 0;
    }
  return 1;
}

static int
valid_directory_response (const struct xos_file_request *request,
                          const struct xos_file_response *response)
{
  const unsigned int identity = request->flags & (1U << 12);
  const unsigned int header = identity ? 13U : 7U;
  const unsigned int limit = request->length ? request->length : 64U;
  if (response->handle != 0 || response->reserved != 0 || response->flags != identity
      || response->value > 0xffffffffULL
      || (response->length == 0 && response->value != 0)
      || (response->value != 0 && response->value <= request->offset)) return 0;
  unsigned int at = 0, count = 0;
  xos_u64 previous = request->offset;
  while (at < response->length)
    {
      if (response->length - at < header || ++count > limit) return 0;
      const unsigned char *record = response->data + at;
      unsigned int length = (unsigned int) record[0] | ((unsigned int) record[1] << 8);
      if (length == 0 || length >= 256 || (record[2] & ~1U) != 0
          || length > response->length - at - header) return 0;
      if (identity)
        {
          unsigned int inode = (unsigned int) record[7] | ((unsigned int) record[8] << 8);
          xos_u32 next = (xos_u32) record[9] | ((xos_u32) record[10] << 8)
            | ((xos_u32) record[11] << 16) | ((xos_u32) record[12] << 24);
          if (inode == 0 || next <= previous) return 0;
          previous = next;
        }
      if (!valid_text (record + header, length, 1)) return 0;
      at += header + length;
    }
  return !identity || response->value == 0 || previous <= response->value;
}

static int
valid_response_shape (unsigned int operation, const struct xos_file_request *request,
                      const struct xos_file_response *response)
{
  if (response->status_code != 0) return response->name_length == 0;
  if (operation == 27 || operation == 28)
    return response->handle == 0 && response->flags == 0 && response->reserved == 0
      && response->length == 0 && response->value == 0 && response->name_length > 0
      && response->name_length < sizeof (response->name) && response->name[0] == '/'
      && response->name[response->name_length] == 0
      && valid_text ((const unsigned char *) response->name, response->name_length, 0);
  if (response->name_length != 0) return 0;
  if (operation == 2) return valid_directory_response (request, response);
  if (operation == 19)
    return response->handle != 0 && response->flags == 0 && response->reserved == 0
      && response->length == 0 && response->value == 0;
  /* anonymous creates a fresh empty regular file and returns the same handle
     and identity fields as open; it must not poison the shared session. */
  if (operation == file_open || operation == file_anonymous)
    return response->length == 0 && response->handle != 0
      && (response->flags & ~1U) == 0 && response->reserved != 0
      && response->reserved <= 65535 && response->value <= 0xfffffffeULL
      && (operation != file_anonymous || (response->flags == 0 && response->value == 0));
  if (operation == file_stat || operation == file_fstat)
    {
      unsigned int allowed_flags = 7U;
      if (operation == file_stat && (request->flags & xos_file_stat_check_exec) != 0)
        allowed_flags |= xos_file_stat_exec_checked;
      return response->handle == 0 && (response->flags & ~allowed_flags) == 0
      && response->reserved != 0 && response->reserved <= 65535
      && response->value <= 0xfffffffeULL
      && (response->length == 0 || response->length == 24);
    }
  if (response->handle != 0 || response->flags != 0 || response->reserved != 0)
    return 0;
  if (operation == 5 || operation == 30)
    return (operation != 30 || request->length <= sizeof (response->data))
      && response->value == response->length && response->length <= request->length;
  if (response->length != 0) return 0;
  if (operation == 6 || operation == 31)
    return request->length <= sizeof (request->data) && response->value <= request->length
      && (response->value != 0 || request->length == 0);
  if (operation == 7) return response->value <= 0xfffffffeULL;
  /* Native block_bench reports the exact completed request, with no payload.
     Its limit is an ABI constant shared with file_abi.hpp, not an IPC length. */
  if (operation == 17)
    return request->length != 0 && request->length <= 8U * 1024U * 1024U
      && response->value == request->length;
  return response->value == 0;
}

long
__xos_file_session_poison (struct xos_file_session *session, int error)
{
  /* A delivered write may have committed. Never replay it on any endpoint. */
  session->phase = xos_file_session_failed;
  return -error;
}

static int
authenticated_handles (xos_u32 handles[2])
{
  return file_trap (22, (xos_u64) handles, 0, 0) == 0
    && handles[0] != 0 && handles[1] != 0 && handles[0] != handles[1];
}

long
__xos_file_session_call_until (struct xos_file_session *session,
                              struct xos_file_request *request,
                              struct xos_file_response *response,
                              xos_u64 phase_deadline)
{
  if (session == 0 || request == 0 || response == 0) return -EFAULT;
  if ((const void *) request == (const void *) response) return -EINVAL;
  if (session->phase != xos_file_session_active) return -EIO;
  if (session->owner_pid == 0)
    {
      const long pid = file_trap (6, 0, 0, 0);
      if (pid <= 0) return __xos_file_session_poison (session, EIO);
      session->owner_pid = (xos_u64) pid;
    }
  if (session->send_handle == 0)
    {
      xos_u32 handles[2] = { 0, 0 };
      if (!authenticated_handles (handles))
        return __xos_file_session_poison (session, EIO);
      session->send_handle = handles[0];
      session->receive_handle = handles[1];
    }
  if (session->request_sequence == ~(xos_u32) 0)
    return __xos_file_session_poison (session, EOVERFLOW);
  long now = file_trap (46, 0, 0, 0);
  if (now < 0 || (xos_u64) now > (xos_u64) LONG_MAX - 5000000000ULL)
    return __xos_file_session_poison (session, EIO);
  if ((xos_u64) now >= phase_deadline)
    return -ETIMEDOUT;
  xos_u64 deadline = (xos_u64) now + 5000000000ULL;
  if (phase_deadline < deadline)
    deadline = phase_deadline;
  request->magic = 0x51455246;
  request->version = 2;
  request->request_id = ++session->request_sequence;
  if (file_trap (4, session->send_handle, (xos_u64) request, sizeof (*request)) != 0)
    return __xos_file_session_poison (session, EIO);
  for (;;)
    {
      const long received = file_trap (5, session->receive_handle, (xos_u64) response,
                                      sizeof (*response));
      now = file_trap (46, 0, 0, 0);
      if (now < 0) return __xos_file_session_poison (session, EIO);
      if ((xos_u64) now >= deadline)
        return __xos_file_session_poison (session, ETIMEDOUT);
      if (received >= 0)
        {
          if (received != sizeof (*response) || response->magic != 0x53455246
              || response->version != 2 || response->request_id != request->request_id
              || response->length > sizeof (response->data)
              || response->name_length >= sizeof (response->name) || response->status_code > 0
              || response->status_code < -16
              || !valid_response_shape (request->operation, request, response))
            return __xos_file_session_poison (session, EIO);
          return __xos_file_service_error (response->status_code);
        }
      if (received != -3) return __xos_file_session_poison (session, EIO);
      /* sys85 mode 4 waits for the authenticated files reply. Old kernels
         return invalid argument for this mode and its nonzero deadline. */
      const long waiting = file_trap (85, session->receive_handle, 4, deadline);
      if (waiting == 0) continue;
      if (waiting == -13) return __xos_file_session_poison (session, ETIMEDOUT);
      if (waiting != -2) return __xos_file_session_poison (session, EIO);
      xos_u64 next = (xos_u64) now + 1000000;
      if (next > deadline) next = deadline;
      if (file_trap (47, next, 0, 0) != 0) return __xos_file_session_poison (session, EIO);
    }
}

long
__xos_file_session_call (struct xos_file_session *session,
                        struct xos_file_request *request,
                        struct xos_file_response *response)
{
  return __xos_file_session_call_until (session, request, response, ~(xos_u64) 0);
}

long
__xos_file_session_take (struct xos_file_session *current, struct xos_file_session *early)
{
  if (current == 0 || early == 0 || current == early) return -EINVAL;
  if (current->owner_pid != 0 || current->request_sequence != 0
      || current->send_handle != 0 || current->receive_handle != 0
      || current->phase != xos_file_session_active) return -EBUSY;
  const long pid = file_trap (6, 0, 0, 0);
  if (pid <= 0 || early->owner_pid != (xos_u64) pid
      || early->phase > xos_file_session_failed) return -EINVAL;
  if (early->phase == xos_file_session_active)
    {
      xos_u32 handles[2] = { 0, 0 };
      if (early->request_sequence == 0 || !authenticated_handles (handles)
          || early->send_handle != handles[0] || early->receive_handle != handles[1])
        return -EIO;
    }
  /* A failed transport is deliberately not authenticated by contacting or
     rebinding its possibly dead peer. It can only stay failed. */
  *current = *early;
  early->phase = xos_file_session_transferred;
  return 0;
}
