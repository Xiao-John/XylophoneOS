/* SPDX-License-Identifier: Apache-2.0
   XOS additions to glibc's x86-64 assembler and syscall definitions.  */
#ifndef XOS_GLIBC_X86_64_SYSDEP_H
#define XOS_GLIBC_X86_64_SYSDEP_H 1
#include_next <sysdep.h>
#ifndef __ASSEMBLER__
# include <syscall_types.h>
# include <xos_thread_exit.h>
/* The current XOS trap ABI has three arguments and no seventh cancel arg. */
# define __SYSCALL_CANCEL7_ARCH_ARG_DEF
/* Only explicitly implemented XOS operations are dispatchable.  In
   particular, this is not a Linux syscall-number compatibility layer. */
# define INTERNAL_SYSCALL_CALL(name, ...) __xos_internal_##name (__VA_ARGS__)
#endif
#endif
