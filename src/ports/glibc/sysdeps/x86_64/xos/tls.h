/* SPDX-License-Identifier: Apache-2.0
   Select the glibc x86-64 NPTL TLS layout with XOS-specific initialization.  */
#ifndef XOS_GLIBC_X86_64_TLS_H
#define XOS_GLIBC_X86_64_TLS_H 1
#define XOS_GLIBC_TLS 1
#include_next <tls.h>
#endif
