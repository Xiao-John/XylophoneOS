/* SPDX-License-Identifier: Apache-2.0 */
#ifndef LWIP_ARCH_CC_H
#define LWIP_ARCH_CC_H
#include <stdint.h>
#include <stddef.h>
#ifndef SSIZE_MAX
#define SSIZE_MAX 0x7fffffff
#endif
typedef uint8_t u8_t;
typedef int8_t s8_t;
typedef uint16_t u16_t;
typedef int16_t s16_t;
typedef uint32_t u32_t;
typedef int32_t s32_t;
typedef uint64_t u64_t;
typedef int64_t s64_t;
typedef uintptr_t mem_ptr_t;
#define U8_F "u"
#define S8_F "d"
#define X8_F "x"
#define U16_F "u"
#define S16_F "d"
#define X16_F "x"
#define U32_F "u"
#define S32_F "d"
#define X32_F "x"
#define SZT_F "zu"
#define PACK_STRUCT_BEGIN
#define PACK_STRUCT_STRUCT __attribute__((packed))
#define PACK_STRUCT_END
#define PACK_STRUCT_FIELD(x) x
#define LWIP_UNUSED_ARG(x) (void)x
#ifdef __cplusplus
extern "C" {
#endif
uint32_t xos_lwip_rand(void);
void xos_lwip_diag(const char* format, ...);
#ifdef __cplusplus
}
#endif
#ifndef LWIP_PLATFORM_DIAG
#define LWIP_PLATFORM_DIAG(x) do { xos_lwip_diag x; } while (0)
#endif
#ifndef LWIP_PLATFORM_ASSERT
#define LWIP_PLATFORM_ASSERT(x) do { xos_lwip_diag("lwip assert: %s", x); for (;;) {} } while (0)
#endif
#endif
