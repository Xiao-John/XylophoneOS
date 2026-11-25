/* SPDX-License-Identifier: Apache-2.0
   Private C view of the existing XOS files v2 and process startup ABI.
   Layout is checked against the canonical shared C++ headers by the host test. */
#ifndef XOS_GLIBC_FILE_WIRE_H
#define XOS_GLIBC_FILE_WIRE_H 1
#include "xos_wait_word.h"
typedef __UINT16_TYPE__ xos_file_u16;
typedef __INT32_TYPE__ xos_file_i32;

struct __attribute__ ((packed)) xos_file_request
{
  xos_u32 magic;
  xos_file_u16 version, operation;
  xos_u32 request_id, handle, flags, reserved;
  xos_u64 offset;
  xos_u32 length, name_length;
  char name[256];
  unsigned char data[3800];
};
struct __attribute__ ((packed)) xos_file_response
{
  xos_u32 magic;
  xos_file_u16 version;
  xos_file_i32 status_code;
  xos_u32 request_id, handle, flags, reserved;
  xos_u64 value;
  xos_u32 length, name_length;
  char name[256];
  unsigned char data[3798];
};
struct xos_file_startup
{
  xos_u64 magic;
  xos_u32 version, size, argc, handle_count;
  xos_u64 argv;
  xos_u32 handles[3], reserved;
};
struct xos_file_startup_extension
{
  xos_u64 magic;
  xos_u32 environment_count, flags;
  xos_u64 environment, working_directory, open_paths[3];
  xos_u32 open_flags[3], file_handles[3], reserved;
};
struct xos_file_startup_descriptor
{
  xos_u32 fd, object, kind, handle, flags, reserved;
};
struct xos_file_startup_exec
{
  xos_u64 magic, descriptors;
  xos_u32 count, reserved;
};
#ifndef __cplusplus
_Static_assert (sizeof (struct xos_file_request) == 4096, "files request ABI");
_Static_assert (sizeof (struct xos_file_response) == 4096, "files response ABI");
_Static_assert (sizeof (struct xos_file_startup) == 48, "startup ABI");
_Static_assert (sizeof (struct xos_file_startup_extension) == 88, "startup v2 ABI");
_Static_assert (sizeof (struct xos_file_startup_descriptor) == 24, "startup fd ABI");
_Static_assert (sizeof (struct xos_file_startup_exec) == 24, "startup exec ABI");
#endif
#endif
