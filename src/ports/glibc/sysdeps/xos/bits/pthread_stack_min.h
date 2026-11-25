/* SPDX-License-Identifier: Apache-2.0
   Lower bound of a native XOS thread stack, in bytes.  The usable minimum for
   a particular glibc thread can be larger when TLS and guard space are needed. */
#ifndef _BITS_PTHREAD_STACK_MIN_H
#define _BITS_PTHREAD_STACK_MIN_H 1
#define PTHREAD_STACK_MIN 65536
#endif
