/* SPDX-License-Identifier: Apache-2.0
   Provisional x86-64 glibc semaphore storage for XOS.  */
#ifndef _SEMAPHORE_H
# error "Never include <bits/semaphore.h> directly; use <semaphore.h>."
#endif
#ifndef _BITS_SEMAPHORE_H
#define _BITS_SEMAPHORE_H 1
#if !defined __x86_64__ || defined __ILP32__
# error "XOS glibc semaphore layout is defined only for x86-64 LP64"
#endif
/* Opaque storage for the selected glibc NPTL implementation.  Its presence
   does not mean that XOS currently implements semaphore operations.  */
#define __SIZEOF_SEM_T 32
typedef union
{
  char __size[__SIZEOF_SEM_T];
  long int __align;
} sem_t;
#define SEM_FAILED ((sem_t *) 0)
#endif
