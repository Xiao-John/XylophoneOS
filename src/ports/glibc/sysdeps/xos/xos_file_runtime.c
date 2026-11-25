/* SPDX-License-Identifier: Apache-2.0
   Process-local FD descriptions over the existing authenticated files session.
   The session lock covers each complete request/reply and its FD mutation.
   Console/pipe waits release that lock while retaining their open description. */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <string.h>
#include <unistd.h>
#include "xos_file_runtime.h"

#ifdef XOS_GLIBC_FILE_TEST
extern long __xos_file_test_trap (xos_u64, xos_u64, xos_u64, xos_u64);
# define file_trap __xos_file_test_trap
#else
static inline long
file_trap (xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
  long result;
  __asm__ volatile ("int $0x80" : "=a" (result)
                    : "a" (number), "D" (first), "S" (second), "d" (third)
                    : "memory", "cc");
  return result;
}
#endif

extern const void *__xos_startup __attribute__ ((weak, visibility ("hidden")));
/* The CRT accepts transferred handles and v3 description snapshots only when
   this backend is linked. Path-based redirection and terminal sessions still
   require a different startup action profile. */
const unsigned int __xos_file_startup_capabilities
  __attribute__ ((visibility ("hidden"))) = 1;
enum { fd_limit = 32, object_limit = 32 };
enum { kind_none, kind_kernel, kind_file, kind_pipe_read, kind_pipe_write };
struct fd_slot { int object; unsigned int close_on_exec; };
struct open_object { unsigned int kind, handle, flags, references; };
static struct fd_slot descriptors[fd_limit];
static struct open_object objects[object_limit];
static xos_u32 session_lock;
static int initialized, initialization_error, session_failed;
static xos_u32 request_sequence, send_handle, receive_handle;
static struct xos_file_request request;
static struct xos_file_response response;

static int
lock_session (void)
{
  while (__atomic_exchange_n (&session_lock, 1, __ATOMIC_ACQUIRE) != 0)
    {
      long result = __xos_wait_word (&session_lock, 1, ~(xos_u64) 0);
      if (result != 0 && result != -14)
        return -EIO;
    }
  return 0;
}

static void
unlock_session (void)
{
  __atomic_store_n (&session_lock, 0, __ATOMIC_RELEASE);
  (void) __xos_wake_word (&session_lock, 1);
}

static long
service_error (int value)
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

static long
kernel_error (long value)
{
  if (value >= 0) return value;
  switch (value)
    {
    case -1: return -EBADF;
    case -2: return -EINVAL;
    case -3: return -EAGAIN;
    case -5: return -ENOMEM;
    case -7: return -EPIPE;
    case -13: return -ETIMEDOUT;
    default: return -EIO;
    }
}

static long
session_fault (int error)
{
  /* A delivered write may have committed. Never replay or attach its old
     handle to another service instance after timeout or malformed reply. */
  session_failed = 1;
  return -error;
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
valid_directory_response (void)
{
  const unsigned int identity = request.flags & (1U << 12);
  const unsigned int header = identity ? 13U : 7U;
  const unsigned int limit = request.length ? request.length : 64U;
  if (response.handle != 0 || response.reserved != 0 || response.flags != identity
      || response.value > 0xffffffffULL
      || (response.length == 0 && response.value != 0)
      || (response.value != 0 && response.value <= request.offset)) return 0;
  unsigned int at = 0, count = 0;
  xos_u64 previous = request.offset;
  while (at < response.length)
    {
      if (response.length - at < header || ++count > limit) return 0;
      const unsigned char *record = response.data + at;
      unsigned int length = (unsigned int) record[0] | ((unsigned int) record[1] << 8);
      if (length == 0 || length >= 256 || (record[2] & ~1U) != 0
          || length > response.length - at - header) return 0;
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
  return !identity || response.value == 0 || previous <= response.value;
}

static int
valid_response_shape (unsigned int operation)
{
  if (response.status_code != 0) return response.name_length == 0;
  if (operation == 27 || operation == 28)
    return response.handle == 0 && response.flags == 0 && response.reserved == 0
      && response.length == 0 && response.value == 0 && response.name_length > 0
      && response.name_length < sizeof (response.name) && response.name[0] == '/'
      && response.name[response.name_length] == 0
      && valid_text ((const unsigned char *) response.name, response.name_length, 0);
  if (response.name_length != 0) return 0;
  if (operation == 2) return valid_directory_response ();
  if (operation == 19)
    return response.handle != 0 && response.flags == 0 && response.reserved == 0
      && response.length == 0 && response.value == 0;
  if (operation == 4)
    return response.length == 0 && response.handle != 0
      && (response.flags & ~1U) == 0 && response.reserved != 0
      && response.reserved <= 65535 && response.value <= 0xfffffffeULL;
  if (operation == 3 || operation == 18)
    return response.handle == 0 && (response.flags & ~7U) == 0
      && response.reserved != 0 && response.reserved <= 65535
      && response.value <= 0xfffffffeULL
      && (response.length == 0 || response.length == 24);
  if (response.handle != 0 || response.flags != 0 || response.reserved != 0)
    return 0;
  if (operation == 5 || operation == 30)
    return (operation != 30 || request.length <= sizeof (response.data))
      && response.value == response.length && response.length <= request.length;
  if (response.length != 0) return 0;
  if (operation == 6 || operation == 31)
    return request.length <= sizeof (request.data) && response.value <= request.length
      && (response.value != 0 || request.length == 0);
  if (operation == 7) return response.value <= 0xfffffffeULL;
  /* Native block_bench reports the exact completed request, with no payload.
     Its limit is an ABI constant shared with file_abi.hpp, not an IPC length. */
  if (operation == 17)
    return request.length != 0 && request.length <= 8U * 1024U * 1024U
      && response.value == request.length;
  return response.value == 0;
}

static long
call_service (unsigned int operation)
{
  if (session_failed) return -EIO;
  if (send_handle == 0)
    {
      xos_u32 handles[2] = { 0, 0 };
      if (file_trap (22, (xos_u64) handles, 0, 0) != 0
          || handles[0] == 0 || handles[1] == 0 || handles[0] == handles[1])
        return session_fault (EIO);
      send_handle = handles[0];
      receive_handle = handles[1];
    }
  if (request_sequence == ~(xos_u32) 0) return session_fault (EOVERFLOW);
  long now = file_trap (46, 0, 0, 0);
  if (now < 0 || (xos_u64) now > (xos_u64) LONG_MAX - 5000000000ULL)
    return session_fault (EIO);
  const xos_u64 deadline = (xos_u64) now + 5000000000ULL;
  request.magic = 0x51455246;
  request.version = 2;
  request.operation = (xos_file_u16) operation;
  request.request_id = ++request_sequence;
  if (file_trap (4, send_handle, (xos_u64) &request, sizeof (request)) != 0)
    return session_fault (EIO);
  for (;;)
    {
      const long received = file_trap (5, receive_handle, (xos_u64) &response,
                                      sizeof (response));
      now = file_trap (46, 0, 0, 0);
      if (now < 0) return session_fault (EIO);
      if ((xos_u64) now >= deadline) return session_fault (ETIMEDOUT);
      if (received >= 0)
        {
          if (received != sizeof (response) || response.magic != 0x53455246
              || response.version != 2 || response.request_id != request.request_id
              || response.length > sizeof (response.data)
              || response.name_length >= sizeof (response.name) || response.status_code > 0
              || response.status_code < -16 || !valid_response_shape (operation))
            return session_fault (EIO);
          return service_error (response.status_code);
        }
      if (received != -3) return session_fault (EIO);
      /* Legacy files endpoints have no deadline-capable readiness wait.
         Sleep on the system monotonic clock; do not invent a retry-count clock. */
      xos_u64 next = (xos_u64) now + 1000000;
      if (next > deadline) next = deadline;
      if (file_trap (47, next, 0, 0) != 0) return session_fault (EIO);
    }
}

static int
prepare_path (const char *path)
{
  return (int) __xos_file_request_path (&request, path);
}

long
__xos_file_request_path (struct xos_file_request *output, const char *path)
{
  if (output == 0) return -EFAULT;
  if (path == 0) return -EFAULT;
  unsigned int length = 0;
  while (length < sizeof (output->name) && path[length] != 0)
    {
      unsigned char value = (unsigned char) path[length];
      if (value < 0x20 || value == 0x7f) return -EINVAL;
      output->name[length] = path[length];
      ++length;
    }
  if (length == 0) return -ENOENT;
  if (length == sizeof (output->name)) return -ENAMETOOLONG;
  output->name[length] = 0;
  output->name_length = length;
  return 0;
}

static int
valid_flags (unsigned int flags)
{
  const unsigned int supported = O_ACCMODE | O_CREAT | O_EXCL | O_TRUNC
    | O_APPEND | O_CLOEXEC | O_NOCTTY | O_DIRECTORY | O_NOFOLLOW | O_NONBLOCK;
  return (flags & ~supported) == 0 && (flags & O_ACCMODE) != O_ACCMODE;
}

static int
valid_startup_range (xos_u64 address, xos_u64 size)
{
#ifdef XOS_GLIBC_FILE_TEST
  extern int __xos_file_test_startup_range (xos_u64, xos_u64);
  return __xos_file_test_startup_range (address, size);
#else
  return address >= 0x7fffc000ULL && address <= 0x80000000ULL
    && size <= 0x80000000ULL - address;
#endif
}

static long close_object (int);
static long open_file (const char *, int);

static int
restore_descriptors (const struct xos_file_startup *startup)
{
  const struct xos_file_startup_exec *exec = (const void *) ((const char *) startup + 152);
  if (!valid_startup_range ((xos_u64) exec, sizeof (*exec))
      || exec->magic != 0x335845534f585546ULL || exec->reserved != 0
      || exec->count > fd_limit || (exec->descriptors & 3) != 0
      || !valid_startup_range (exec->descriptors,
                              (xos_u64) exec->count * sizeof (struct xos_file_startup_descriptor)))
    return -EINVAL;
  const struct xos_file_startup_descriptor *items = (const void *) exec->descriptors;
  unsigned int cleanup[object_limit] = { 0 };
  memset (objects, 0, sizeof (objects));
  for (int i = 0; i < fd_limit; ++i) descriptors[i].object = -1;
  for (unsigned int i = 0; i < exec->count; ++i)
    {
      const struct xos_file_startup_descriptor *item = &items[i];
      if (item->object >= object_limit || item->kind < kind_kernel
          || item->kind > kind_pipe_write || item->reserved != 0
          || !valid_flags (item->flags)
          || (item->kind == kind_kernel && item->handle > 2)
          || (item->kind == kind_file && item->handle == 0)
          || (item->kind >= kind_pipe_read && item->handle < 65536)
          || (item->fd != ~(xos_u32) 0 && item->fd >= fd_limit))
        return -EINVAL;
      struct open_object *object = &objects[item->object];
      if (object->kind != 0
          && (object->kind != item->kind || object->handle != item->handle
              || object->flags != item->flags))
        return -EINVAL;
      if (object->kind == 0)
        {
          /* One ownership record per actual handle; aliases name an object. */
          for (int j = 0; j < object_limit; ++j)
            if (objects[j].kind == item->kind && objects[j].handle == item->handle)
              return -EINVAL;
          *object = (struct open_object) { item->kind, item->handle, item->flags, 0 };
        }
      if (item->fd == ~(xos_u32) 0)
        {
          if (cleanup[item->object] || object->references) return -EINVAL;
          cleanup[item->object] = 1;
        }
      else
        {
          if (cleanup[item->object] || descriptors[item->fd].object >= 0)
            return -EINVAL;
          descriptors[item->fd] = (struct fd_slot) { (int) item->object, 0 };
          ++object->references;
        }
    }
  /* Validate the whole list before any close; malformed later entries cannot
     cause early destruction of an inherited object. */
  for (int i = 0; i < object_limit; ++i)
    if (cleanup[i])
      {
        objects[i].references = 1;
        long result = close_object (i);
        if (result < 0) return (int) result;
      }
  return 0;
}

static int
initialize (void)
{
  if (initialized) return initialization_error;
  initialized = 1;
  for (int i = 0; i < fd_limit; ++i) descriptors[i].object = -1;
  const struct xos_file_startup *startup = &__xos_startup ? __xos_startup : 0;
  if (startup != 0
      && (((xos_u64) startup & 7) != 0
          || !valid_startup_range ((xos_u64) startup, sizeof (*startup))
          || startup->magic != 0x3154524154535358ULL || startup->size != 48
          || startup->version < 1 || startup->version > 3 || startup->handle_count != 3
          || (startup->version == 1 ? startup->reserved != 0 : startup->reserved != 64)))
    return initialization_error = -EINVAL;
  for (int i = 0; i < 3; ++i)
    {
      const unsigned int handle = startup ? startup->handles[i] : (unsigned int) i;
      if (handle > 2) return initialization_error = -EINVAL;
      objects[i] = (struct open_object) { kind_kernel, handle,
        (unsigned int) (i == 0 ? O_RDONLY : O_WRONLY), 1 };
      descriptors[i].object = i;
    }
  if (startup == 0 || startup->version == 1) return 0;
  const struct xos_file_startup_extension *extension =
    (const void *) ((const char *) startup + 64);
  if (!valid_startup_range ((xos_u64) extension, sizeof (*extension))
      || extension->magic != 0x32585445534f5855ULL
      || extension->environment_count > 64 || extension->reserved != 0
      || (extension->flags & ~0x10707U) != 0)
    return initialization_error = -EINVAL;
  if (extension->flags & 0x10000U) return initialization_error = -ENOTSUP;
  if (startup->version == 3)
    return initialization_error = restore_descriptors (startup);
  for (int i = 0; i < 3; ++i)
    {
      if ((extension->flags & (1U << i)) != 0)
        {
          objects[i] = (struct open_object) { 0 };
          descriptors[i].object = -1;
        }
      if ((extension->flags & (1U << (8 + i))) != 0)
        {
          if (extension->file_handles[i] == 0 || !valid_flags (extension->open_flags[i])
              || extension->open_paths[i] != 0)
            return initialization_error = -EINVAL;
          for (int previous = 0; previous < i; ++previous)
            if (objects[previous].kind == kind_file
                && objects[previous].handle == extension->file_handles[i])
              return initialization_error = -EINVAL;
          objects[i] = (struct open_object) { kind_file, extension->file_handles[i],
                                            extension->open_flags[i], 1 };
          descriptors[i].object = i;
        }
      else if (extension->open_paths[i] != 0)
        {
          /* Path-based spawn redirection is not inherited open-description
             state. It needs a separate loader action profile. */
          return initialization_error = -ENOTSUP;
        }
      else if (extension->file_handles[i] != 0 || extension->open_flags[i] != 0)
        return initialization_error = -EINVAL;
    }
  return 0;
}

static int
begin (void)
{
  int result = lock_session ();
  if (result != 0) return result;
  result = initialize ();
  if (result != 0) unlock_session ();
  return result;
}

static int
object_for (int fd)
{
  if (fd < 0 || fd >= fd_limit) return -1;
  return descriptors[fd].object;
}

static int
free_descriptor (int minimum)
{
  for (int i = minimum; i < fd_limit; ++i)
    if (descriptors[i].object < 0) return i;
  return -1;
}

static long
open_file (const char *path, int flags)
{
  if (!valid_flags ((unsigned int) flags)) return -EINVAL;
  int fd = free_descriptor (0), index = -1;
  for (int i = 0; i < object_limit; ++i)
    if (objects[i].references == 0) { index = i; break; }
  if (fd < 0 || index < 0) return -EMFILE;
  memset (&request, 0, sizeof (request));
  long result = prepare_path (path);
  if (result != 0) return result;
  request.flags = (unsigned int) (flags & O_ACCMODE) + 1;
  if (flags & O_CREAT) request.flags |= 4;
  if (flags & O_EXCL) request.flags |= 8;
  if (flags & O_TRUNC) request.flags |= 16;
  if (flags & O_APPEND) request.flags |= 32;
  if (flags & O_DIRECTORY) request.flags |= 1024;
  if (request.name[request.name_length - 1] == '/') request.flags |= 1024;
  result = call_service (4);
  if (result != 0) return result;
  if (response.handle == 0 || response.length != 0 || response.value > 0xfffffffeULL)
    return session_fault (EIO);
  if ((response.flags & 1) != ((request.flags & 1024) != 0))
    return session_fault (EIO);
  for (int i = 0; i < object_limit; ++i)
    if (objects[i].kind == kind_file && objects[i].handle == response.handle)
      return session_fault (EIO);
  objects[index] = (struct open_object) { kind_file, response.handle,
    ((unsigned int) flags & (O_ACCMODE | O_APPEND | O_NONBLOCK))
      | (response.flags & 1 ? O_DIRECTORY : 0), 1 };
  descriptors[fd] = (struct fd_slot) { index, (flags & O_CLOEXEC) != 0 };
  return fd;
}

long
__xos_file_open (const char *path, int flags)
{
  int error = begin ();
  if (error != 0) return error;
  long result = open_file (path, flags);
  unlock_session ();
  return result;
}

static long
close_object (int index)
{
  struct open_object *object = &objects[index];
  if (--object->references != 0) return 0;
  long result;
  if (object->kind == kind_file)
    {
      memset (&request, 0, sizeof (request));
      request.handle = object->handle;
      result = call_service (8);
      if (result == 0 && response.length != 0) result = session_fault (EIO);
    }
  else result = kernel_error (file_trap (object->kind == kind_kernel ? 13 : 33,
                                        object->handle, 0, 0));
  /* The FD has already been removed. A close error must never make retry
     accidentally close a later FD that reused its number. */
  *object = (struct open_object) { 0 };
  return result;
}

long
__xos_file_close (int fd)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index >= 0)
    {
      descriptors[fd] = (struct fd_slot) { -1, 0 };
      result = close_object (index);
    }
  unlock_session ();
  return result;
}

static long
stream_io (struct open_object object, void *buffer, size_t length, int writing)
{
  const int console = object.kind == kind_kernel
    && file_trap (34, 0, object.handle, 0) == 1;
  if (writing && console && length > 256) length = 256;
  const unsigned int number = object.kind == kind_kernel ? (writing ? 11 : 12)
    : (writing ? 32 : 31);
  const int atomic_write = writing && !console && length <= 4096;
  const xos_u64 handle = object.handle | (atomic_write ? 1ULL << 63 : 0);
  for (;;)
    {
      long result = file_trap (number, handle, (xos_u64) buffer, length);
      if (result >= 0)
        {
          if ((size_t) result > length) return -EIO;
          if (!writing && console)
            {
              unsigned char *bytes = buffer;
              for (long i = 0; i < result; ++i)
                if (bytes[i] == '\r') bytes[i] = '\n';
            }
          return result;
        }
      if (result != -3 || (object.flags & O_NONBLOCK)) return kernel_error (result);
      if (!console)
        {
          result = file_trap (54, object.handle, atomic_write ? length : writing ? 1 : 0, 0);
          if (result < 0) return kernel_error (result);
        }
      else
        {
          long now = file_trap (46, 0, 0, 0);
          if (now < 0 || now > LONG_MAX - 1000000) return -EIO;
          if (file_trap (47, (xos_u64) now + 1000000, 0, 0) != 0) return -EIO;
        }
    }
}

static long
file_io (int fd, void *buffer, size_t length, int writing)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index < 0) goto done;
  struct open_object *object = &objects[index];
  if ((object->flags & O_ACCMODE) == (unsigned int) (writing ? O_RDONLY : O_WRONLY)
      || object->kind == (unsigned int) (writing ? kind_pipe_read : kind_pipe_write))
    goto done;
  if (buffer == 0 && length != 0) { result = -EFAULT; goto done; }
  if (length == 0) { result = 0; goto done; }
  if (length > (size_t) LONG_MAX) length = LONG_MAX;
  if (object->kind != kind_file)
    {
      ++object->references;
      struct open_object copy = *object;
      unlock_session ();
      result = stream_io (copy, buffer, length, writing);
      /* A lease retains the actual route while another thread closes the FD. */
      error = lock_session ();
      if (error != 0) return error;
      (void) close_object (index);
      goto done;
    }
  if (object->flags & O_DIRECTORY) { result = -EISDIR; goto done; }
  memset (&request, 0, sizeof (request));
  const size_t capacity = writing ? sizeof (request.data) : sizeof (response.data);
  if (length > capacity) length = capacity;
  request.handle = object->handle;
  request.length = (xos_u32) length;
  if (writing) memcpy (request.data, buffer, length);
  result = call_service (writing ? 6 : 5);
  if (result != 0) goto done;
  if (writing)
    {
      if (response.length != 0 || response.value > length)
        result = session_fault (EIO);
      else result = (long) response.value;
    }
  else if (response.length > length) result = session_fault (EIO);
  else { memcpy (buffer, response.data, response.length); result = response.length; }
done:
  unlock_session ();
  return result;
}

long __xos_file_read (int fd, void *buffer, size_t length)
{ return file_io (fd, buffer, length, 0); }
long __xos_file_write (int fd, const void *buffer, size_t length)
{ return file_io (fd, (void *) buffer, length, 1); }

long
__xos_file_seek (int fd, long offset, int origin)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index < 0) goto done;
  if (objects[index].kind != kind_file) { result = -ESPIPE; goto done; }
  if (origin < 0 || origin > 2) { result = -EINVAL; goto done; }
  memset (&request, 0, sizeof (request));
  request.handle = objects[index].handle;
  request.offset = (xos_u64) offset;
  request.flags = (unsigned int) origin;
  result = call_service (7);
  if (result == 0)
    result = response.length == 0 && response.value <= 0xfffffffeULL
      ? (long) response.value : session_fault (EIO);
done:
  unlock_session ();
  return result;
}

static long
decode_stat (struct stat *output)
{
  if (response.value > 0xfffffffeULL || (response.flags & ~7U) != 0
      || response.reserved > 65535)
    return session_fault (EIO);
  struct stat value;
  memset (&value, 0, sizeof (value));
  value.st_dev = 1;
  value.st_ino = response.reserved;
  value.st_mode = (response.flags & 1 ? S_IFDIR : S_IFREG) | 0777;
  value.st_nlink = response.flags & 2 ? 0 : 1;
  value.st_size = (long) response.value;
#ifdef _STATBUF_ST_BLKSIZE
  value.st_blksize = 512;
  value.st_blocks = (long) ((response.value + 511) / 512);
#endif
  if (response.length != 0)
    {
      const unsigned char *data = response.data;
      if (response.length != 24 || memcmp (data, "FMET\1\0\30\0", 8) != 0)
        return session_fault (EIO);
      xos_u64 seconds = 0;
      xos_u32 nanoseconds = 0, mode = 0;
      for (unsigned int i = 0; i < 8; ++i) seconds |= (xos_u64) data[8 + i] << (8 * i);
      for (unsigned int i = 0; i < 4; ++i)
        { nanoseconds |= (xos_u32) data[16 + i] << (8 * i); mode |= (xos_u32) data[20 + i] << (8 * i); }
      if (seconds > (xos_u64) LONG_MAX || nanoseconds >= 1000000000
          || (mode & S_IFMT) != (response.flags & 1 ? S_IFDIR : S_IFREG)
          || (mode & ~(S_IFMT | 0777U)) != 0)
        return session_fault (EIO);
      value.st_mode = mode;
      value.st_atime = value.st_mtime = value.st_ctime = (long) seconds;
      value.st_atim.tv_nsec = value.st_mtim.tv_nsec = value.st_ctim.tv_nsec = nanoseconds;
    }
  *output = value;
  return 0;
}

long
__xos_file_stat (int fd, const char *path, struct stat *output)
{
  int error = begin ();
  if (error != 0) return error;
  long result;
  if (output == 0) { result = -EFAULT; goto done; }
  memset (&request, 0, sizeof (request));
  if (path == 0)
    {
      int index = object_for (fd);
      if (index < 0) { result = -EBADF; goto done; }
      struct open_object *object = &objects[index];
      if (object->kind != kind_file)
        {
          memset (output, 0, sizeof (*output));
          long console = object->kind == kind_kernel ? file_trap (34, 0, object->handle, 0) : 0;
          if (console < 0) { result = kernel_error (console); goto done; }
          output->st_mode = (console ? S_IFCHR : S_IFIFO) | 0600;
          output->st_nlink = 1;
#ifdef _STATBUF_ST_BLKSIZE
          output->st_blksize = 512;
#endif
          result = 0; goto done;
        }
      request.handle = object->handle;
    }
  else
    {
      result = prepare_path (path);
      if (result != 0) goto done;
    }
  result = call_service (path == 0 ? 18 : 3);
  if (result == 0) result = decode_stat (output);
done:
  unlock_session ();
  return result;
}

long
__xos_file_dup (int fd, int target, int exact, int close_on_exec)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index < 0 || (exact && (target < 0 || target >= fd_limit))) goto done;
  if (!exact && (target < 0 || target >= fd_limit)) { result = -EINVAL; goto done; }
  if (exact && fd == target) { result = close_on_exec ? -EINVAL : fd; goto done; }
  if (!exact) target = free_descriptor (target);
  if (target < 0) { result = -EMFILE; goto done; }
  const int previous = descriptors[target].object;
  ++objects[index].references;
  descriptors[target] = (struct fd_slot) { index, close_on_exec != 0 };
  if (previous >= 0) (void) close_object (previous);
  result = target;
done:
  unlock_session ();
  return result;
}

long
__xos_file_fcntl (int fd, int command, int argument)
{
  if (command == F_DUPFD || command == F_DUPFD_CLOEXEC)
    return __xos_file_dup (fd, argument, 0, command == F_DUPFD_CLOEXEC);
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index < 0) goto done;
  if (command == F_GETFD) result = descriptors[fd].close_on_exec ? FD_CLOEXEC : 0;
  else if (command == F_SETFD)
    {
      if ((argument & ~FD_CLOEXEC) != 0) result = -EINVAL;
      else { descriptors[fd].close_on_exec = argument != 0; result = 0; }
    }
  else if (command == F_GETFL)
    result = objects[index].flags & (O_ACCMODE | O_APPEND | O_NONBLOCK | O_DIRECTORY);
  else if (command == F_SETFL)
    {
      const unsigned int old = objects[index].flags;
      if ((argument & ~(O_ACCMODE | O_APPEND | O_NONBLOCK | O_DIRECTORY)) != 0
          || (((unsigned int) argument ^ old) & O_APPEND) != 0)
        result = -ENOTSUP;
      else { objects[index].flags = (old & ~(unsigned int) O_NONBLOCK)
          | ((unsigned int) argument & O_NONBLOCK); result = 0; }
    }
  else result = -ENOTSUP;
done:
  unlock_session ();
  return result;
}

long
__xos_file_path_op (const char *path, int operation)
{
  int error = begin ();
  if (error != 0) return error;
  memset (&request, 0, sizeof (request));
  long result = prepare_path (path);
  if (result == 0)
    {
      request.flags = operation == 513 ? 512 : 0;
      result = call_service (operation == 513 ? 13 : (unsigned int) operation);
      if (result == 0 && response.length != 0) result = session_fault (EIO);
    }
  unlock_session ();
  return result;
}

long
__xos_file_truncate (int fd, long length)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index < 0) goto done;
  if (objects[index].kind != kind_file) { result = -EINVAL; goto done; }
  if ((objects[index].flags & O_ACCMODE) == O_RDONLY) { result = -EBADF; goto done; }
  if (length < 0) { result = -EINVAL; goto done; }
  if ((xos_u64) length > 0xfffffffeULL) { result = -EFBIG; goto done; }
  memset (&request, 0, sizeof (request));
  request.handle = objects[index].handle; request.offset = (xos_u64) length;
  result = call_service (25);
  if (result == 0 && response.length != 0) result = session_fault (EIO);
done:
  unlock_session ();
  return result;
}

long
__xos_file_sync (int fd)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index >= 0)
    {
      if (objects[index].kind != kind_file) result = -EINVAL;
      else
        {
          memset (&request, 0, sizeof (request));
          result = call_service (14);
          if (result == 0 && response.length != 0) result = session_fault (EIO);
        }
    }
  unlock_session ();
  return result;
}

long
__xos_file_isatty (int fd)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index >= 0)
    {
      if (objects[index].kind != kind_kernel) result = -ENOTTY;
      else
        {
          result = file_trap (34, 0, objects[index].handle, 0);
          result = result == 1 ? 1 : result == 0 ? -ENOTTY : kernel_error (result);
        }
    }
  unlock_session ();
  return result;
}

long
__xos_file_lease_acquire (int fd, int access, struct xos_file_lease *lease)
{
  if (lease == 0) return -EFAULT;
  *lease = (struct xos_file_lease) { .object = -1 };
  if (access < -1 || access > 1) return -EINVAL;
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = index < 0 ? -EBADF : 0;
  if (index >= 0)
    {
      struct open_object *object = &objects[index];
      unsigned int mode = object->flags & O_ACCMODE;
      if ((access == 0 && mode == O_WRONLY) || (access == 1 && mode == O_RDONLY))
        result = -EBADF;
      else if (object->references == ~(unsigned int) 0)
        result = -EOVERFLOW;
      else
        {
          ++object->references;
          *lease = (struct xos_file_lease) { index, object->kind, object->handle, object->flags };
        }
    }
  unlock_session ();
  return result;
}

long
__xos_file_lease_release (struct xos_file_lease *lease)
{
  if (lease == 0) return -EFAULT;
  if (lease->object < 0 || lease->object >= object_limit) return -EINVAL;
  int error = lock_session ();
  if (error != 0) return error;
  struct open_object *object = &objects[lease->object];
  long result = -EINVAL;
  if (object->references != 0 && object->kind == lease->kind && object->handle == lease->handle)
    {
      result = close_object (lease->object);
      *lease = (struct xos_file_lease) { .object = -1 };
    }
  unlock_session ();
  return result;
}

long
__xos_file_exchange (const struct xos_file_request *input, struct xos_file_response *output)
{
  if (input == 0 || output == 0) return -EFAULT;
  /* Callers own disjoint request and response records. */
  if ((const void *) input == (const void *) output) return -EINVAL;
  memset (output, 0, sizeof (*output));
  int error = begin ();
  if (error != 0) return error;
  request = *input;
  long result = call_service (request.operation);
  if (result == 0) *output = response;
  unlock_session ();
  return result;
}

long
xos_file_session_exchange (const struct xos_file_request *input, struct xos_file_response *output)
{
  long result = __xos_file_exchange (input, output);
  switch (result)
    {
    case 0: return 0;
    case -ENOENT: return -1;
    case -EINVAL: return -2;
    case -EMFILE: return -3;
    case -ENOSPC: return -4;
    case -EBUSY: return -5;
    case -EBADF: return -6;
    case -EAGAIN: return -8;
    case -EEXIST: return -9;
    case -ENOTDIR: return -10;
    case -EISDIR: return -11;
    case -ENOTEMPTY: return -12;
    case -ENAMETOOLONG: return -13;
    case -ENOTSUP: return -14;
    case -EROFS: return -15;
    case -EACCES: return -16;
    default: return -7;
    }
}
