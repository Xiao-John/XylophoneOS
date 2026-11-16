/* SPDX-License-Identifier: Apache-2.0
   Make generic NPTL futex declarations self-contained for XOS.  */
#ifndef XOS_GLIBC_FUTEX_INTERNAL_H
#define XOS_GLIBC_FUTEX_INTERNAL_H 1
#include <errno.h>
#include <time.h>
#include <atomic.h>
#include_next <futex-internal.h>
#endif
