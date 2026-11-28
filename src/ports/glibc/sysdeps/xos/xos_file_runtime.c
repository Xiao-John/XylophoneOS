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
#include "xos_net2_socket.h"
#include "xos_terminal_runtime.h"

#include "xos_file_trap.h"

#ifdef SHARED
# include "xos_d1_start.h"
#else
extern const void *__xos_startup __attribute__ ((weak, visibility ("hidden")));
#endif
/* The backend and its strongly linked terminal adapter provide file (bit0)
   and terminal (bit1) startup. Path-based redirection remains separate. */
const unsigned int __xos_file_startup_capabilities
  __attribute__ ((visibility ("hidden"))) = 3;
enum { fd_limit = 32, object_limit = 32 };
enum { kind_none, kind_kernel, kind_file, kind_pipe_read, kind_pipe_write, kind_terminal, kind_socket };
_Static_assert (kind_socket == (int) xos_file_kind_socket, "FD socket route identity");
struct fd_slot { int object; unsigned int close_on_exec; };
struct open_object { unsigned int kind, handle, flags, references; };
static struct fd_slot descriptors[fd_limit];
static struct open_object objects[object_limit];
static xos_u32 poll_releases[object_limit];
static xos_u32 session_lock, spawn_cwd_lock;
static int initialized, initialization_error;
static struct xos_file_session session;
static struct xos_file_request request;
static struct xos_file_response response;
enum { pipe_create = 30, pipe_read = 31, pipe_write = 32, pipe_close = 33,
       pipe_wait = 54, pipe_token_min = 65536, pipe_capacity = 4096 };
/* The files service reserves this identity for its synthetic /dev namespace. */
enum { file_device_directory_inode = 0xfffe };

static int
lock_runtime_until (xos_u32 *lock, xos_u64 deadline)
{
  for (;;)
    {
      if (deadline != ~(xos_u64) 0)
        {
          const long now = file_trap (46, 0, 0, 0);
          if (now < 0) return -EIO;
          if ((xos_u64) now >= deadline) return -ETIMEDOUT;
        }
      if (__atomic_exchange_n (lock, 1, __ATOMIC_ACQUIRE) == 0) return 0;
      long result = __xos_wait_word (lock, 1, deadline);
      if (result == -13) return -ETIMEDOUT;
      if (result != 0 && result != -14)
        return -EIO;
    }
}

static int lock_runtime (xos_u32 *lock)
{ return lock_runtime_until (lock, ~(xos_u64) 0); }

static void
unlock_runtime (xos_u32 *lock)
{
  __atomic_store_n (lock, 0, __ATOMIC_RELEASE);
  (void) __xos_wake_word (lock, 1);
}

static int lock_session (void) { return lock_runtime (&session_lock); }
static void unlock_session (void) { unlock_runtime (&session_lock); }

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
  return __xos_file_session_poison (&session, error);
}

static long
call_service_until (unsigned int operation, xos_u64 deadline)
{
  request.operation = (xos_file_u16) operation;
  return __xos_file_session_call_until (&session, &request, &response, deadline);
}

static long
call_service (unsigned int operation)
{
  return call_service_until (operation, ~(xos_u64) 0);
}

#ifndef SHARED
long
__xos_file_adopt_early_session (struct xos_file_session *early)
{
  long result = lock_session ();
  if (result != 0) return result;
  result = initialized ? -EBUSY : __xos_file_session_take (&session, early);
  unlock_session ();
  return result;
}
#endif

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

static long close_object_until (int, xos_u64);

static int
restore_descriptors (const struct xos_file_startup *startup, int terminal_startup,
                     xos_u64 deadline)
{
  const struct xos_file_startup_exec *exec = (const void *) ((const char *) startup + 152);
  if (!valid_startup_range ((xos_u64) exec, sizeof (*exec))
      || exec->magic != 0x335845534f585546ULL || exec->reserved != 0
      || exec->count > fd_limit
      || exec->descriptors % _Alignof (struct xos_file_startup_descriptor) != 0
      || !valid_startup_range (exec->descriptors,
                              (xos_u64) exec->count * sizeof (struct xos_file_startup_descriptor)))
    return -EINVAL;
  const struct xos_file_startup_descriptor *items = (const void *) exec->descriptors;
  unsigned int cleanup[object_limit] = { 0 };
  int terminal_object = -1;
  memset (objects, 0, sizeof (objects));
  for (int i = 0; i < fd_limit; ++i) descriptors[i].object = -1;
  for (unsigned int i = 0; i < exec->count; ++i)
    {
      const struct xos_file_startup_descriptor *item = &items[i];
      if (item->object >= object_limit || item->kind < kind_kernel
          || item->kind > kind_terminal || item->reserved != 0
          || !valid_flags (item->flags)
          || (item->kind == kind_kernel && item->handle > 2)
          || (item->kind == kind_file && item->handle == 0)
          || ((item->kind == kind_pipe_read || item->kind == kind_pipe_write)
              && item->handle < pipe_token_min)
          || (item->kind == kind_terminal && (item->handle != 0
              || item->fd == ~(xos_u32) 0 || !terminal_startup))
          || (item->fd != ~(xos_u32) 0 && item->fd >= fd_limit))
        return -EINVAL;
      if (item->kind == kind_terminal)
        {
          if (item->flags != O_RDWR) return -ENOTSUP;
          terminal_object = (int) item->object;
        }
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
  /* Validate the whole list before connecting or closing. A malformed later
     entry cannot consume a terminal sequence or destroy inherited objects. */
  if ((terminal_object >= 0) != terminal_startup) return -EINVAL;
  if (terminal_startup)
    {
      struct terminal_exec { xos_u64 magic, next_sequence; };
      const struct terminal_exec *terminal = (const void *) ((const char *) startup + 176);
      if (!valid_startup_range ((xos_u64) terminal, sizeof (*terminal))
          || terminal->magic != 0x33595454534f5858ULL || terminal->next_sequence == 0)
        return -EINVAL;
      long result = __xos_terminal_restore (startup);
      if (result < 0) return (int) result;
    }
  for (int i = 0; i < object_limit; ++i)
    if (cleanup[i])
      {
        objects[i].references = 1;
        long result = close_object_until (i, deadline);
        if (result < 0)
          {
            if (terminal_startup) (void) __xos_terminal_close ();
            return (int) result;
          }
      }
  return 0;
}

static int
valid_startup_header (const struct xos_file_startup *startup)
{
  return ((xos_u64) startup & 7) == 0
    && valid_startup_range ((xos_u64) startup, sizeof (*startup))
    && startup->magic == 0x3154524154535358ULL && startup->size == 48
    && startup->version >= 1 && startup->version <= 3 && startup->handle_count == 3
    && startup->reserved == (startup->version == 1 ? 0 : 64);
}

static int
initialize_from (const struct xos_file_startup *startup, xos_u64 deadline)
{
  initialized = 1;
  for (int i = 0; i < fd_limit; ++i) descriptors[i].object = -1;
  if (startup != 0 && !valid_startup_header (startup))
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
      || extension->environment_count > 64
      || ((extension->flags & 0x10000U) == 0 ? extension->reserved != 0
                                            : extension->reserved == 0)
      || (extension->flags & ~0x10707U) != 0)
    return initialization_error = -EINVAL;
  const int terminal_startup = (extension->flags & 0x10000U) != 0;
  if (startup->version == 3)
    return initialization_error = restore_descriptors (startup, terminal_startup, deadline);
  if (terminal_startup)
    {
      if (extension->flags != 0x10007U) return initialization_error = -EINVAL;
      for (int i = 0; i < 3; ++i)
        if (extension->open_paths[i] != 0 || extension->file_handles[i] != 0
            || extension->open_flags[i] != 0) return initialization_error = -EINVAL;
      long result = __xos_terminal_restore (startup);
      if (result < 0) return initialization_error = (int) result;
      memset (objects, 0, sizeof (objects));
      objects[0] = (struct open_object) { kind_terminal, 0, O_RDWR, 3 };
      for (int i = 0; i < 3; ++i) descriptors[i] = (struct fd_slot) { 0, 0 };
      return 0;
    }
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

#ifdef SHARED
long
__xos_file_adopt_startup (struct xos_file_session *early, xos_u64 deadline)
{
  long result = lock_session ();
  if (result != 0) return result;
  const struct xos_file_startup *startup = (const void *) XOS_D1_STARTUP_BEGIN;
  const long now = file_trap (46, 0, 0, 0);
  if (initialized)
    result = -EBUSY;
  else if (early == NULL || deadline == 0 || deadline > LONG_MAX
           || !valid_startup_header (startup))
    result = -EINVAL;
  else if (early->phase != xos_file_session_active || now < 0)
    result = -EIO;
  else if ((xos_u64) now >= deadline)
    result = -ETIMEDOUT;
  else
    {
      result = __xos_file_session_take (&session, early);
      if (result == 0)
        {
          result = initialize_from (startup, deadline);
          const long finished = file_trap (46, 0, 0, 0);
          if (result == 0 && (finished < 0 || (xos_u64) finished >= deadline))
            result = initialization_error = finished < 0 ? -EIO : -ETIMEDOUT;
        }
    }
  unlock_session ();
#ifdef XOS_PUBLIC_DYNAMIC_STARTUP
  if (result == 0)
    {
      extern long xos_dynamic_adopt_startup (xos_u64) __attribute__ ((visibility ("hidden")));
      result = xos_dynamic_adopt_startup (deadline);
    }
#endif
  return result;
}
#endif

static int
initialize_until (xos_u64 deadline)
{
  if (initialized) return initialization_error;
#ifdef SHARED
  /* The relocated libc has no CRT-owned startup state. Its caller must
     adopt the real descriptors and authenticated session before use. */
  (void) deadline;
  return -EIO;
#else
  const struct xos_file_startup *startup = &__xos_startup ? __xos_startup : 0;
  return initialize_from (startup, deadline);
#endif
}

/* A queued release owns a counted reference, so its object cannot be reused
   until drained under session_lock. Poll never performs the last remote close. */
static void
drain_poll_releases (int allow_io)
{
  for (int index = 0; index < object_limit; ++index)
    {
      xos_u32 count = __atomic_exchange_n (&poll_releases[index], 0, __ATOMIC_ACQUIRE);
      if (!count) continue;
      struct open_object *object = &objects[index];
      if (object->references > count) object->references -= count;
      else if (object->references == count && (allow_io || object->kind == kind_socket))
        {
          object->references = 1;
          (void) close_object_until (index, ~(xos_u64) 0);
        }
      else (void) __atomic_fetch_add (&poll_releases[index], count, __ATOMIC_RELEASE);
    }
}

static int
begin_until (xos_u64 deadline)
{
  int result = lock_runtime_until (&session_lock, deadline);
  if (result != 0) return result;
  result = initialize_until (deadline);
  if (result != 0) unlock_session ();
  else drain_poll_releases (1);
  return result;
}

static int begin (void) { return begin_until (~(xos_u64) 0); }

#ifndef SHARED
static long
fork_deadline_status (xos_u64 deadline)
{
  const long now = file_trap (46, 0, 0, 0);
  if (now < 0) return -EIO;
  return (xos_u64) now >= deadline ? -ETIMEDOUT : 0;
}

static long
fork_error (long result)
{
  switch (result)
    {
    case -1: return -EPERM;
    case -5: return -EAGAIN;
    case -11: return -EBUSY;
    case -18: return -ENOTSUP;
    default: return -EIO;
    }
}

/* The kernel copies the FD table's native pipe references, memory, and TLS.
   The files service separately retains the open descriptions and cwd under
   the authenticated child identity. Commit only after both have succeeded. */
long
__xos_file_fork (void)
{
  long result = begin ();
  if (result != 0) return result;
  int terminal_inherited = 0;
  for (unsigned int i = 0; i < object_limit; ++i)
    if (objects[i].references != 0)
      {
        if (objects[i].kind == kind_socket)
          { unlock_session (); return -ENOTSUP; }
        if (objects[i].kind == kind_terminal) terminal_inherited = 1;
      }

  const long now = file_trap (46, 0, 0, 0);
  if (now < 0 || now > LONG_MAX - 5000000000L)
    {
      unlock_session ();
      return -EIO;
    }
  const xos_u64 deadline = (xos_u64) now + 5000000000ULL;
  const long child = file_trap (57, 0, 0, 0);
  if (child == 0)
    {
      /* The copied session endpoints are owned by the parent. The first
         child request obtains its new authenticated endpoints and sequence. */
      memset (&session, 0, sizeof (session));
      __xos_net2_after_fork ();
      if (terminal_inherited) __xos_terminal_fork_child ();
    }
  else if (child < 0)
    result = fork_error (child);
  else
    {
      result = fork_deadline_status (deadline);
      if (result == 0 && terminal_inherited)
        result = __xos_terminal_fork_prepare ((xos_u64) child, deadline);
      if (result == 0)
        {
          do
            {
              memset (&request, 0, sizeof (request));
              request.operation = file_clone_session;
              request.offset = (xos_u64) child;
              result = __xos_file_session_call_until (&session, &request, &response, deadline);
            }
          while (result == -EAGAIN);
        }
      if (result == 0)
        result = fork_deadline_status (deadline);
      if (result == 0)
        {
          const long committed = file_trap (58, (xos_u64) child, 0, 0);
          result = committed == 0 ? child : fork_error (committed);
        }
      if (result < 0)
        (void) file_trap (19, (xos_u64) child, 0, 0);
    }
  unlock_session ();
  return result;
}
#endif

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

static int
free_object (int minimum)
{
  for (int i = minimum; i < object_limit; ++i)
    if (objects[i].references == 0) return i;
  return -1;
}

long
__xos_file_socket (int close_on_exec)
{
  int error = lock_session ();
  if (error) return error;
  drain_poll_releases (0);
  unlock_session ();
  __xos_net2_reap ();
  error = begin ();
  if (error) return error;
  int fd = free_descriptor (0), index = free_object (0);
  long result = -EMFILE;
  if (fd >= 0 && index >= 0)
    {
      result = __xos_net2_alloc ();
      if (result >= 0)
        {
          objects[index] = (struct open_object) { kind_socket, (unsigned int) result, O_RDWR, 1 };
          descriptors[fd] = (struct fd_slot) { index, close_on_exec != 0 };
          result = fd;
        }
    }
  unlock_session ();
  return result;
}

static long
open_file (const char *path, int flags, unsigned int operation)
{
  if (!valid_flags ((unsigned int) flags)) return -EINVAL;
  int fd = free_descriptor (0), index = free_object (0);
  if (fd < 0 || index < 0) return -EMFILE;
  memset (&request, 0, sizeof (request));
  if (operation == file_open)
    {
      long prepared = prepare_path (path);
      if (prepared != 0) return prepared;
      request.flags = (unsigned int) (flags & O_ACCMODE) + 1;
      if (flags & O_CREAT) request.flags |= 4;
      if (flags & O_EXCL) request.flags |= 8;
      if (flags & O_TRUNC) request.flags |= 16;
      if (flags & O_APPEND) request.flags |= 32;
      if (flags & O_DIRECTORY) request.flags |= 1024;
      if (request.name[request.name_length - 1] == '/') request.flags |= 1024;
    }
  long result = call_service (operation);
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
  long result = open_file (path, flags, file_open);
  unlock_session ();
  return result;
}

long
__xos_file_open_anonymous (void)
{
  int error = begin ();
  if (error != 0) return error;
  long result = open_file (0, O_RDWR | O_CLOEXEC, file_anonymous);
  unlock_session ();
  return result;
}

long
__xos_file_seal_anonymous (int fd)
{
  int error = begin ();
  if (error != 0) return error;
  int index = object_for (fd);
  long result = -EBADF;
  if (index >= 0)
    {
      struct open_object *object = &objects[index];
      result = -EINVAL;
      if (object->kind == kind_file)
        {
          memset (&request, 0, sizeof (request));
          request.handle = object->handle;
          result = call_service (file_anonymous_seal);
          if (result == 0)
            object->flags = (object->flags & ~(unsigned int) O_ACCMODE) | O_RDONLY;
        }
    }
  unlock_session ();
  return result;
}

long
__xos_file_pipe (int output[2], int flags)
{
  if (output == 0) return -EFAULT;
  if ((flags & ~(O_CLOEXEC | O_NONBLOCK)) != 0) return -EINVAL;
  int error = begin ();
  if (error != 0) return error;

  /* Reserve two of each in the same locked transaction. Native allocation
     begins only after local capacity has been checked. */
  int reader = free_descriptor (0);
  int writer = reader < 0 ? -1 : free_descriptor (reader + 1);
  int read_object = free_object (0);
  int write_object = read_object < 0 ? -1 : free_object (read_object + 1);
  long result = -EMFILE;
  if (writer >= 0 && write_object >= 0)
    {
      xos_u32 tokens[2] = { 0, 0 };
      long created = file_trap (pipe_create, (xos_u64) tokens, 0, 0);
      if (created < 0)
        result = created == -5 ? -ENFILE : kernel_error (created);
      else if (created != 0 || tokens[0] < pipe_token_min
               || tokens[1] < pipe_token_min || tokens[0] == tokens[1])
        {
          if (tokens[0] >= pipe_token_min)
            (void) file_trap (pipe_close, tokens[0], 0, 0);
          if (tokens[1] >= pipe_token_min && tokens[1] != tokens[0])
            (void) file_trap (pipe_close, tokens[1], 0, 0);
          result = -EIO;
        }
      else
        {
          unsigned int status = (unsigned int) flags & O_NONBLOCK;
          unsigned int close_on_exec = (flags & O_CLOEXEC) != 0;
          objects[read_object] = (struct open_object) {
            kind_pipe_read, tokens[0], status | O_RDONLY, 1 };
          objects[write_object] = (struct open_object) {
            kind_pipe_write, tokens[1], status | O_WRONLY, 1 };
          descriptors[reader] = (struct fd_slot) { read_object, close_on_exec };
          descriptors[writer] = (struct fd_slot) { write_object, close_on_exec };
          output[0] = reader;
          output[1] = writer;
          result = 0;
        }
    }
  unlock_session ();
  return result;
}

static long
close_object_until (int index, xos_u64 deadline)
{
  struct open_object *object = &objects[index];
  if (--object->references != 0) return 0;
  long result;
  if (object->kind == kind_file)
    {
      memset (&request, 0, sizeof (request));
      request.handle = object->handle;
      result = call_service_until (8, deadline);
      if (result == 0 && response.length != 0) result = session_fault (EIO);
    }
  else if (object->kind == kind_terminal) result = __xos_terminal_close ();
  else if (object->kind == kind_socket)
    { __xos_net2_retire (object->handle); result = 0; }
  else result = kernel_error (file_trap (object->kind == kind_kernel ? 13 : pipe_close,
                                        object->handle, 0, 0));
  /* The FD has already been removed. A close error must never make retry
     accidentally close a later FD that reused its number. */
  *object = (struct open_object) { 0 };
  return result;
}

static long
close_object (int index)
{
  return close_object_until (index, ~(xos_u64) 0);
}

long
__xos_file_spawn_begin (struct xos_spawn_stdio *stdio)
{
  int error = lock_runtime (&spawn_cwd_lock);
  if (error != 0) return error;
  error = begin ();
  if (error == 0)
    {
      for (int fd = 0; fd < fd_limit; ++fd)
        {
          int index = object_for (fd);
          if (descriptors[fd].close_on_exec) index = -1;
          if (fd >= 3)
            {
              if (index >= 0) { error = -ENOTSUP; break; }
              continue;
            }
          stdio->object[fd] = index;
          stdio->route[fd] = -2;
          stdio->file_handle[fd] = 0;
          stdio->open_flags[fd] = 0;
          if (index < 0) continue;
          const struct open_object *object = &objects[index];
          if (object->kind == kind_file)
            {
              stdio->route[fd] = -1;
              stdio->file_handle[fd] = object->handle;
              stdio->open_flags[fd] = object->flags;
            }
          else if ((object->flags & O_NONBLOCK) == 0
                   && ((object->kind == kind_kernel
                        && (fd == 0) == (object->handle == 0))
                       || object->kind == (unsigned int) (fd == 0 ? kind_pipe_read
                                                                 : kind_pipe_write)))
            stdio->route[fd] = object->handle;
          else
            {
              error = -ENOTSUP;
              break;
            }
        }
      if (error == 0)
        for (int fd = 0; fd < 3; ++fd)
          if (stdio->object[fd] >= 0) ++objects[stdio->object[fd]].references;
      unlock_session ();
    }
  if (error != 0) unlock_runtime (&spawn_cwd_lock);
  return error;
}

void
__xos_file_spawn_end (struct xos_spawn_stdio *stdio)
{
  if (lock_session () == 0)
    {
      for (int fd = 0; fd < 3; ++fd)
        if (stdio->object[fd] >= 0) (void) close_object (stdio->object[fd]);
      unlock_session ();
    }
  unlock_runtime (&spawn_cwd_lock);
}

long
__xos_file_exec_begin (struct xos_exec_descriptors *snapshot, xos_u64 deadline)
{
  if (snapshot == NULL || deadline == 0 || deadline > LONG_MAX) return -EINVAL;
  memset (snapshot, 0, sizeof (*snapshot));
  long error = lock_runtime_until (&spawn_cwd_lock, deadline);
  if (error != 0) return error;
  error = begin_until (deadline);
  if (error != 0) { unlock_runtime (&spawn_cwd_lock); return error; }
  unsigned int kept[object_limit] = { 0 };
  int terminal = 0;
  for (int fd = 0; fd < fd_limit; ++fd)
    {
      const int index = object_for (fd);
      if (index < 0 || descriptors[fd].close_on_exec) continue;
      const struct open_object *object = &objects[index];
      if (object->kind == kind_socket) { error = -ENOTSUP; break; }
      kept[index] = 1;
      terminal |= object->kind == kind_terminal;
      snapshot->items[snapshot->count++] = (struct xos_file_startup_descriptor) {
        (xos_u32) fd, (xos_u32) index, object->kind, object->handle,
        object->flags & ~(unsigned int) O_CLOEXEC, 0
      };
    }
  for (int index = 0; error == 0 && index < object_limit; ++index)
    {
      const struct open_object *object = &objects[index];
      if (object->kind == kind_socket && object->references) { error = -ENOTSUP; break; }
      if (object->kind == kind_none || kept[index] || object->kind == kind_terminal) continue;
      if (snapshot->count == fd_limit) { error = -EMFILE; break; }
      snapshot->items[snapshot->count++] = (struct xos_file_startup_descriptor) {
        ~(xos_u32) 0, (xos_u32) index, object->kind, object->handle,
        object->flags & ~(unsigned int) O_CLOEXEC, 0
      };
    }
  if (error == 0)
    for (int index = 0; index < object_limit; ++index)
      if (objects[index].kind != kind_none && objects[index].references)
        { ++objects[index].references; snapshot->retained[index] = 1; }
  unlock_session ();
  if (error != 0) { unlock_runtime (&spawn_cwd_lock); return error; }
  if (terminal)
    {
      error = __xos_terminal_exec_begin (snapshot->terminal_channels,
                                         &snapshot->terminal_sequence, deadline);
      if (error == 0) snapshot->terminal_locked = 1;
      else __xos_file_exec_end (snapshot, deadline);
    }
  return error;
}

void
__xos_file_exec_end (struct xos_exec_descriptors *snapshot, xos_u64 deadline)
{
  if (snapshot->terminal_locked) __xos_terminal_exec_end ();
  if (lock_runtime_until (&session_lock, deadline) == 0)
    {
      for (int index = 0; index < object_limit; ++index)
        if (snapshot->retained[index]) (void) close_object_until (index, deadline);
      unlock_session ();
    }
  else
    for (int index = 0; index < object_limit; ++index)
      if (snapshot->retained[index])
        (void) __atomic_fetch_add (&poll_releases[index], 1, __ATOMIC_RELEASE);
  unlock_runtime (&spawn_cwd_lock);
}

static long
close_descriptor (int fd)
{
  int index = object_for (fd);
  if (index < 0) return -EBADF;
  descriptors[fd] = (struct fd_slot) { -1, 0 };
  return close_object (index);
}

long
__xos_file_close (int fd)
{
  int error = begin ();
  if (error != 0) return error;
  long result = close_descriptor (fd);
  unlock_session ();
  __xos_net2_reap ();
  return result;
}

long
__xos_file_close_range (unsigned int first, unsigned int last)
{
  if (first > last) return -EINVAL;
  if (first >= fd_limit) return 0;
  int error = begin ();
  if (error != 0) return error;
  /* Closing retires the descriptor even if its final release reports an
     error. The range operation ignores those individual close results. */
  for (unsigned int fd = first; fd < fd_limit && fd <= last; ++fd)
    (void) close_descriptor ((int) fd);
  unlock_session ();
  __xos_net2_reap ();
  return 0;
}

static long
stream_io (struct open_object object, void *buffer, size_t length, int writing)
{
  if (object.kind == kind_socket)
    return __xos_net2_stream (object.handle, buffer, length, writing);
  if (object.kind == kind_terminal)
    return writing ? __xos_terminal_write (buffer, length, object.flags)
                   : __xos_terminal_read (buffer, length, object.flags);
  const int console = object.kind == kind_kernel
    && file_trap (34, 0, object.handle, 0) == 1;
  if (writing && console && length > 256) length = 256;
  const unsigned int number = object.kind == kind_kernel ? (writing ? 11 : 12)
    : (writing ? pipe_write : pipe_read);
  const int atomic_write = writing && !console && length <= pipe_capacity;
  const int blocking_pipe_write = writing && !console && !(object.flags & O_NONBLOCK);
  const xos_u64 handle = object.handle | (atomic_write ? 1ULL << 63 : 0);
  size_t done = 0;
  for (;;)
    {
      long result = file_trap (number, handle, (xos_u64) ((unsigned char *) buffer + done),
                               length - done);
      if (result >= 0)
        {
          if ((size_t) result > length - done) return -EIO;
          if (!writing && console)
            {
              unsigned char *bytes = buffer;
              for (long i = 0; i < result; ++i)
                if (bytes[i] == '\r') bytes[i] = '\n';
            }
          done += (size_t) result;
          if (!blocking_pipe_write || done == length || result == 0) return (long) done;
          continue;
        }
      if (result != -3 || (object.flags & O_NONBLOCK))
        return done != 0 ? (long) done : kernel_error (result);
      if (!console)
        {
          result = file_trap (pipe_wait, object.handle, atomic_write ? length : writing ? 1 : 0, 0);
          if (result < 0) return done != 0 ? (long) done : kernel_error (result);
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
      if (copy.kind == kind_socket)
        {
          unlock_session ();
          __xos_net2_reap ();
          return result;
        }
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
  if (response.value > 0xfffffffeULL || (response.flags & ~(7U | xos_file_stat_exec_checked)) != 0
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

static long
stat_path (const char *path, struct stat *output, unsigned int flags)
{
  long result = prepare_path (path);
  request.flags = flags;
  if (result == 0) result = call_service (file_stat);
  if (result == 0 && (flags & xos_file_stat_check_exec) != 0
      && (response.flags & xos_file_stat_exec_checked) == 0)
    return -ENOTSUP;
  return result == 0 ? decode_stat (output) : result;
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
          long console = object->kind == kind_terminal ? 1
            : object->kind == kind_kernel ? file_trap (34, 0, object->handle, 0) : 0;
          if (console < 0) { result = kernel_error (console); goto done; }
          output->st_mode = (object->kind == kind_socket ? S_IFSOCK : console ? S_IFCHR : S_IFIFO) | 0600;
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
      result = stat_path (path, output, 0);
      goto done;
    }
  result = call_service (file_fstat);
  if (result == 0) result = decode_stat (output);
done:
  unlock_session ();
  return result;
}

long
__xos_file_getcwd (char *output, size_t capacity)
{
  int error = begin ();
  if (error != 0) return error;
  memset (&request, 0, sizeof (request));
  long result = call_service (file_cwd_get);
  if (result == 0)
    {
      size_t length = response.name_length + 1;
      if (length > capacity) result = -ERANGE;
      else
        {
          memcpy (output, response.name, length);
          result = (long) length;
        }
    }
  unlock_session ();
  return result;
}

static long
access_mode (const struct stat *status, int mode)
{
  if ((mode & R_OK) != 0 && (status->st_mode & S_IRUSR) == 0) return -EACCES;
  if ((mode & W_OK) != 0 && ((status->st_mode & S_IWUSR) == 0
                            || status->st_ino == file_device_directory_inode))
    return -EACCES;
  if ((mode & X_OK) != 0 && S_ISDIR (status->st_mode)
      && (status->st_mode & S_IXUSR) == 0) return -EACCES;
  return 0;
}

long
__xos_file_access (const char *path, int mode)
{
  if ((mode & ~(R_OK | W_OK | X_OK)) != 0) return -EINVAL;
  int error = begin ();
  if (error != 0) return error;
  struct stat status;
  memset (&request, 0, sizeof (request));
  long result = stat_path (path, &status, (mode & X_OK) != 0 ? xos_file_stat_check_exec : 0);
  if (result == 0) result = access_mode (&status, mode);
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
  __xos_net2_reap ();
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
          || (((unsigned int) argument ^ old) & O_APPEND) != 0
          || ((objects[index].kind == kind_terminal || objects[index].kind == kind_socket)
              && (argument & O_NONBLOCK) != 0))
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
  const int changes_cwd = (xos_file_u16) operation == file_cwd_set;
  int error = changes_cwd ? lock_runtime (&spawn_cwd_lock) : 0;
  if (error != 0) return error;
  long result = begin ();
  if (result == 0)
    {
      memset (&request, 0, sizeof (request));
      result = prepare_path (path);
      if (result == 0)
        {
          request.flags = operation == 513 ? 512 : 0;
          result = call_service (operation == 513 ? 13 : (unsigned int) operation);
          if (result == 0 && response.length != 0) result = session_fault (EIO);
        }
      unlock_session ();
    }
  if (changes_cwd) unlock_runtime (&spawn_cwd_lock);
  return result;
}

long
__xos_file_chdir (const char *path)
{
  return __xos_file_path_op (path, file_cwd_set);
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
      if (objects[index].kind == kind_terminal) result = 1;
      else if (objects[index].kind != kind_kernel) result = -ENOTTY;
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
__xos_file_poll_lease_acquire (int fd, struct xos_file_lease *lease)
{
  if (!lease) return -EFAULT;
  *lease = (struct xos_file_lease) { .object = -1 };
  if (fd < 0 || fd >= fd_limit) return -EBADF;
  if (__atomic_exchange_n (&session_lock, 1, __ATOMIC_ACQUIRE) != 0) return -EAGAIN;
  long result = !initialized ? -EOPNOTSUPP : initialization_error;
  if (!result)
    {
      drain_poll_releases (0);
      int index = object_for (fd);
      if (index < 0) result = -EBADF;
      else
        {
          struct open_object *object = &objects[index];
          if (object->references == ~(unsigned int) 0) result = -EOVERFLOW;
          else
            {
              ++object->references;
              *lease = (struct xos_file_lease) { index, object->kind, object->handle, object->flags };
            }
        }
    }
  unlock_session ();
  return result;
}

void
__xos_file_poll_lease_release (struct xos_file_lease *lease)
{
  if (!lease || lease->object < 0 || lease->object >= object_limit) return;
  (void) __atomic_fetch_add (&poll_releases[lease->object], 1, __ATOMIC_RELEASE);
  lease->object = -1;
  if (__atomic_exchange_n (&session_lock, 1, __ATOMIC_ACQUIRE) == 0)
    {
      drain_poll_releases (0);
      unlock_session ();
    }
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
  __xos_net2_reap ();
  return result;
}

static long
exchange_until (const struct xos_file_request *input, struct xos_file_response *output,
                xos_u64 deadline)
{
  if (input == 0 || output == 0) return -EFAULT;
  /* Callers own disjoint request and response records. */
  if ((const void *) input == (const void *) output) return -EINVAL;
  memset (output, 0, sizeof (*output));
  /* Match the service's self selectors. Spawn already owns the cwd lock
     while the loader sets the new child's directory through this exchange. */
  const int changes_cwd = input->operation == file_cwd_set
    && (input->offset == 0 || input->offset == (xos_u64) file_trap (6, 0, 0, 0));
  int error = changes_cwd ? lock_runtime_until (&spawn_cwd_lock, deadline) : 0;
  if (error != 0) return error;
  long result = begin_until (deadline);
  if (result == 0)
    {
      request = *input;
      result = call_service_until (request.operation, deadline);
      if (result == 0) *output = response;
      unlock_session ();
    }
  if (changes_cwd) unlock_runtime (&spawn_cwd_lock);
  return result;
}

long
__xos_file_exchange (const struct xos_file_request *input, struct xos_file_response *output)
{
  return exchange_until (input, output, ~(xos_u64) 0);
}

static long
native_exchange_result (long result)
{
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
    case -ETIMEDOUT: return -1001;
    default: return -7;
    }
}

long
xos_file_session_exchange (const struct xos_file_request *input, struct xos_file_response *output)
{
  return native_exchange_result (__xos_file_exchange (input, output));
}

long
xos_file_session_exchange_until (const struct xos_file_request *input,
                                 struct xos_file_response *output, xos_u64 deadline)
{
  if (deadline == 0 || deadline > LONG_MAX) return -2;
  return native_exchange_result (exchange_until (input, output, deadline));
}
