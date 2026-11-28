/* SPDX-License-Identifier: Apache-2.0
   Static startup is implemented by the XOS CRT and libc-tls.c.
   A dynamic interpreter requires its own loader/startup protocol. */
#if defined(SHARED) && !defined(XOS_PUBLIC_DYNAMIC_STARTUP)
# error "XOS dynamic interpreter startup is not implemented"
#endif
