/* SPDX-License-Identifier: Apache-2.0
   libc-local requests: translated in userspace, never kernel ioctl numbers. */
#ifndef _SYS_IOCTL_H
# error "Include <sys/ioctl.h> before this implementation header."
#endif
#ifndef _XOS_BITS_IOCTLS_H
#define _XOS_BITS_IOCTLS_H 1
#define TCGETS 0x5401UL
#define TCSETS 0x5402UL
#define TCSETSW 0x5403UL
#define TCSETSF 0x5404UL
#define FIONCLEX 0x5450UL
#define FIOCLEX 0x5451UL
#endif
