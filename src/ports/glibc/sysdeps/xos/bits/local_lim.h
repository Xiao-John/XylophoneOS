/* SPDX-License-Identifier: Apache-2.0
   Provisional limits for the XOS glibc thread runtime.  */
#ifndef _BITS_LOCAL_LIM_H
#define _BITS_LOCAL_LIM_H 1
/* Thread-specific keys are managed in userspace; these sizes configure
   glibc's own tables and do not enlarge the XOS per-process thread quota.  */
#define _POSIX_THREAD_KEYS_MAX 128
#define PTHREAD_KEYS_MAX 128
#define _POSIX_THREAD_DESTRUCTOR_ITERATIONS 4
#define PTHREAD_DESTRUCTOR_ITERATIONS 4
/* Conservative NPTL value bound, also representable by int. */
#define SEM_VALUE_MAX 2147483647
/* XOS file-service paths are bounded UTF-8 byte strings (max_name in
   xos/file_abi.hpp). NAME_MAX excludes the terminator. */
#define NAME_MAX 255
#define PATH_MAX 256
/* Matches the native process_pipe_bytes capacity and atomic write limit. */
#define PIPE_BUF 4096
#endif
