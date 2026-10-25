/* SPDX-License-Identifier: Apache-2.0 */
#ifndef _SYS__PTHREADTYPES_H_
#define _SYS__PTHREADTYPES_H_
#include <stddef.h>
#include <stdint.h>
typedef uint64_t pthread_t;
typedef uint32_t pthread_key_t;
typedef struct { uint32_t unsupported; } pthread_rwlock_t;
typedef struct { uint32_t lock, waiters; uint64_t owner; uint32_t depth, type, valid, reserved; } pthread_mutex_t;
typedef struct { uint32_t sequence, waiters; int clock; uint32_t valid; } pthread_cond_t;
typedef struct { uint32_t state, reserved; uint64_t owner; } pthread_once_t;
typedef struct { size_t stacksize; void* stackaddr; int detachstate, valid; } pthread_attr_t;
typedef struct { int type, valid; } pthread_mutexattr_t;
typedef struct { int clock, valid; } pthread_condattr_t;
#endif
