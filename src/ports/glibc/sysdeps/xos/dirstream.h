/* SPDX-License-Identifier: Apache-2.0
   XOS directory streams remain opaque until the file-service backend is
   implemented.  Code needing their layout must fail to compile rather than
   relying on a made-up structure or claiming directory operations work.  */
#ifndef XOS_GLIBC_DIRSTREAM_H
#define XOS_GLIBC_DIRSTREAM_H 1
struct __dirstream;
#endif
