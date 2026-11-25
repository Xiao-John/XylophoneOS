/* SPDX-License-Identifier: Apache-2.0
   Bounded directory pages over an owned files handle, with real inode/cookies. */
#include "xos_file_directory.h"
#include "dirstream.h"
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>

enum { list_operation = 2, identity_flag = 1u << 12, directory_flag = 1u << 8 };

static long
lock_directory (DIR *directory)
{
  while (__atomic_exchange_n (&directory->lock, 1, __ATOMIC_ACQUIRE) != 0)
    {
      long error = __xos_wait_word (&directory->lock, 1, ~(xos_u64) 0);
      if (error != 0 && error != -14) return -EIO;
    }
  return 0;
}

static void
unlock_directory (DIR *directory)
{
  __atomic_store_n (&directory->lock, 0, __ATOMIC_RELEASE);
  (void) __xos_wake_word (&directory->lock, 1);
}

long
__xos_directory_open (int fd, DIR **result)
{
  struct xos_file_lease lease;
  long error = __xos_file_lease_acquire (fd, 0, &lease);
  if (error < 0) return error;
  if (lease.kind != xos_file_kind_file || (lease.flags & O_DIRECTORY) == 0)
    {
      (void) __xos_file_lease_release (&lease);
      return -ENOTDIR;
    }
  DIR *directory = calloc (1, sizeof (*directory));
  if (directory == NULL)
    {
      (void) __xos_file_lease_release (&lease);
      return -ENOMEM;
    }
  directory->fd = fd;
  directory->lease = lease;
  *result = directory;
  return 0;
}

long
__xos_directory_close (DIR *directory)
{
  if (directory == NULL) return -EINVAL;
  long closed = __xos_file_close (directory->fd);
  long released = __xos_file_lease_release (&directory->lease);
  free (directory);
  return closed < 0 ? closed : released;
}

static xos_u32
little32 (const unsigned char *value)
{
  return (xos_u32) value[0] | ((xos_u32) value[1] << 8)
    | ((xos_u32) value[2] << 16) | ((xos_u32) value[3] << 24);
}

static long
read_locked (DIR *directory, struct dirent **result)
{
  *result = NULL;
  if (directory->page_position == directory->page_length)
    {
      if (directory->end) return 0;
      struct xos_file_request request = { 0 };
      struct xos_file_response response;
      request.operation = list_operation;
      request.handle = directory->lease.handle;
      request.flags = identity_flag | directory_flag;
      request.offset = directory->cursor;
      request.length = 64;
      long error = __xos_file_exchange (&request, &response);
      if (error < 0) return error;
      /* exchange validates every record before publishing any of this page. */
      memcpy (directory->page, response.data, response.length);
      directory->page_position = 0;
      directory->page_length = response.length;
      directory->page_next = (xos_u32) response.value;
      directory->end = response.value == 0;
      if (response.length == 0) return 0;
    }
  const unsigned char *record = directory->page + directory->page_position;
  unsigned int length = (unsigned int) record[0] | ((unsigned int) record[1] << 8);
  struct dirent *entry = (struct dirent *) directory->entry.bytes;
  _Static_assert (__builtin_offsetof (struct dirent, d_name) + 256 <= 512,
                  "directory entry storage");
  memset (&directory->entry, 0, sizeof (directory->entry));
  entry->d_ino = (unsigned long) record[7] | ((unsigned long) record[8] << 8);
  entry->d_type = (record[2] & 1) != 0 ? DT_DIR : DT_REG;
  entry->d_reclen = (unsigned short) (__builtin_offsetof (struct dirent, d_name) + length + 1);
#ifdef _DIRENT_HAVE_D_NAMLEN
  entry->d_namlen = (unsigned char) length;
#endif
  memcpy (entry->d_name, record + 13, length);
  entry->d_name[length] = '\0';
  directory->cursor = little32 (record + 9);
#ifdef _DIRENT_HAVE_D_OFF
  entry->d_off = directory->cursor;
#endif
  directory->page_position += 13 + length;
  if (directory->page_position == directory->page_length && directory->page_next != 0)
    directory->cursor = directory->page_next;
  *result = entry;
  return 1;
}

long
__xos_directory_read (DIR *directory, struct dirent **result)
{
  if (directory == NULL || result == NULL) return -EINVAL;
  long locked = lock_directory (directory);
  if (locked < 0) { *result = NULL; return locked; }
  long error = read_locked (directory, result);
  unlock_directory (directory);
  return error;
}

long
__xos_directory_read_copy (DIR *directory, struct dirent *entry, struct dirent **result)
{
  if (directory == NULL || entry == NULL || result == NULL) return -EINVAL;
  long locked = lock_directory (directory);
  if (locked < 0) { *result = NULL; return locked; }
  struct dirent *current = NULL;
  long error = read_locked (directory, &current);
  *result = NULL;
  if (error > 0)
    {
      memcpy (entry, current, current->d_reclen);
      *result = entry;
    }
  unlock_directory (directory);
  return error;
}

long
__xos_directory_seek (DIR *directory, long position)
{
  if (directory == NULL || position < 0 || (unsigned long) position > 0xffffffffUL)
    return -EINVAL;
  long locked = lock_directory (directory);
  if (locked < 0) return locked;
  directory->cursor = (xos_u32) position;
  directory->page_position = directory->page_length = directory->page_next = 0;
  directory->end = 0;
  unlock_directory (directory);
  return 0;
}

long
__xos_directory_tell (DIR *directory)
{
  if (directory == NULL) return -EINVAL;
  long locked = lock_directory (directory);
  if (locked < 0) return locked;
  long result = directory->cursor;
  unlock_directory (directory);
  return result;
}
