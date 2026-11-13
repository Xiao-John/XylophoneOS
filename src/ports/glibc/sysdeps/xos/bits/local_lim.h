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
#endif
