/* SPDX-License-Identifier: Apache-2.0
   Provisional XOS glibc errno namespace.  Numeric values are userspace ABI,
   not raw kernel or service result codes; each backend must translate them.
   The initial assignments match the existing XOS SDK where names overlap.
   This header does not import or depend on newlib implementation details.  */
#ifndef _BITS_ERRNO_H
#define _BITS_ERRNO_H 1
#ifndef _ERRNO_H
# error "Never include <bits/errno.h> directly; use <errno.h>."
#endif
#define E2BIG 7
#define EACCES 13
#define EADDRINUSE 112
#define EADDRNOTAVAIL 125
#define EAFNOSUPPORT 106
#define EAGAIN 11
#define EALREADY 120
#define EBADF 9
#define EBADMSG 77
#define EBUSY 16
#define ECANCELED 140
#define ECHILD 10
#define ECONNABORTED 113
#define ECONNREFUSED 111
#define ECONNRESET 104
#define EDEADLK 45
#define EDESTADDRREQ 121
#define EDOM 33
#define EDQUOT 132
#define EEXIST 17
#define EFAULT 14
#define EFBIG 27
#define EFTYPE 79
#define EHOSTDOWN 117
#define EHOSTUNREACH 118
#define EIDRM 36
#define EILSEQ 138
#define EINPROGRESS 119
#define EINTR 4
#define EINVAL 22
#define EIO 5
#define EISCONN 127
#define EISDIR 21
#define ELOOP 92
#define EMFILE 24
#define EMLINK 31
#define EMSGSIZE 122
#define EMULTIHOP 74
#define ENAMETOOLONG 91
#define ENETDOWN 115
#define ENETRESET 126
#define ENETUNREACH 114
#define ENFILE 23
#define ENOBUFS 105
#define ENODATA 61
#define ENODEV 19
#define ENOENT 2
#define ENOEXEC 8
#define ENOLCK 46
#define ENOLINK 67
#define ENOMEM 12
#define ENOMSG 35
#define ENOPROTOOPT 109
#define ENOSPC 28
#define ENOSR 63
#define ENOSTR 60
#define ENOSYS 88
#define ENOTCONN 128
#define ENOTDIR 20
#define ENOTEMPTY 90
#define ENOTRECOVERABLE 141
#define ENOTSOCK 108
#define ENOTSUP 134
#define ENOTTY 25
#define ENXIO 6
#define EOPNOTSUPP 95
#define EOVERFLOW 139
#define EOWNERDEAD 142
#define EPERM 1
#define EPFNOSUPPORT 96
#define EPIPE 32
#define EPROTO 71
#define EPROTONOSUPPORT 123
#define EPROTOTYPE 107
#define ERANGE 34
#define EROFS 30
#define ESPIPE 29
#define ESRCH 3
#define ESTALE 133
#define ETIME 62
#define ETIMEDOUT 116
#define ETOOMANYREFS 129
#define ETXTBSY 26
#define EWOULDBLOCK EAGAIN
#define EXDEV 18
#endif
