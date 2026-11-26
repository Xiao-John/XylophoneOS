/* SPDX-License-Identifier: Apache-2.0 */
#pragma once

#include <time.h>

#undef MBEDTLS_FS_IO
#undef MBEDTLS_PSA_CRYPTO_STORAGE_C
#undef MBEDTLS_PSA_ITS_FILE_C
#undef MBEDTLS_PSA_BUILTIN_GET_ENTROPY
#define MBEDTLS_PSA_DRIVER_GET_ENTROPY
#define MBEDTLS_PLATFORM_TIME_MACRO xos_tls_wall_time
#define MBEDTLS_PLATFORM_GMTIME_R_ALT
#define MBEDTLS_PLATFORM_MS_TIME_ALT

#if !defined(MBEDTLS_HAVE_TIME) || !defined(MBEDTLS_HAVE_TIME_DATE)
#error "XOS TLS requires upstream certificate validity time checks"
#endif

#ifdef __cplusplus
extern "C" {
#endif
time_t xos_tls_wall_time(time_t *out);
#ifdef __cplusplus
}
#endif
