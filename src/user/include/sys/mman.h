/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stddef.h>
#include <sys/types.h>
#define PROT_NONE 0
#define PROT_READ 1
#define PROT_WRITE 2
#define PROT_EXEC 4
#define MAP_SHARED 0x01
#define MAP_PRIVATE 0x02
#define MAP_FIXED 0x10
#define MAP_ANONYMOUS 0x20
#define MAP_ANON MAP_ANONYMOUS
#define MAP_FIXED_NOREPLACE 0x100000
#define MAP_FAILED ((void *)-1)
#ifdef __cplusplus
extern "C" {
#endif
void *mmap(void *, size_t, int, int, int, off_t);
int mprotect(void *, size_t, int);
int munmap(void *, size_t);
#ifdef __cplusplus
}
#endif
