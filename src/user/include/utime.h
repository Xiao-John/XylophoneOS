/* SPDX-License-Identifier: Apache-2.0 */
/* newlib's generic <sys/utime.h> defines struct utimbuf but declares no utime();
   XOS provides the implementation, so declare it here for user programs. */
#ifndef _XOS_UTIME_H
#define _XOS_UTIME_H

#include <sys/types.h>
#include <sys/utime.h>

#ifdef __cplusplus
extern "C" {
#endif

int utime(const char* path, const struct utimbuf* times);

#ifdef __cplusplus
}
#endif

#endif
