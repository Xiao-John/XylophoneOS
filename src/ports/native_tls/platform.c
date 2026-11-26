/* SPDX-License-Identifier: Apache-2.0 */
#include <mbedtls/platform.h>
#include <mbedtls/platform_util.h>
#include <psa/crypto.h>
#include <sys/random.h>
#include <time.h>

int mbedtls_platform_get_entropy(psa_driver_get_entropy_flags_t flags,
                                 size_t *estimate_bits,
                                 unsigned char *output, size_t size)
{
    *estimate_bits = 0;
    if (flags || size > SIZE_MAX / 8)
        return PSA_ERROR_NOT_SUPPORTED;
    for (size_t offset = 0; offset < size;) {
        const size_t remaining = size - offset;
        const size_t request = remaining < 256 ? remaining : 256;
        const ssize_t count = getrandom(output + offset, request, 0);
        if (count <= 0 || (size_t) count > request) {
            mbedtls_platform_zeroize(output, size);
            return PSA_ERROR_INSUFFICIENT_ENTROPY;
        }
        offset += (size_t) count;
    }
    *estimate_bits = size * 8;
    return PSA_SUCCESS;
}

time_t xos_tls_wall_time(time_t *out)
{
    struct timespec sample;
    time_t result = -1;
    if (clock_gettime(CLOCK_REALTIME, &sample) == 0 && sample.tv_sec >= 0)
        result = sample.tv_sec;
    if (out)
        *out = result;
    return result;
}

struct tm *mbedtls_platform_gmtime_r(const mbedtls_time_t *value, struct tm *out)
{
    // Preserve the clock failure through the X.509 validity checks.
    return *value < 0 ? NULL : gmtime_r(value, out);
}

mbedtls_ms_time_t mbedtls_ms_time(void)
{
    struct timespec sample;
    if (clock_gettime(CLOCK_MONOTONIC, &sample) || sample.tv_sec < 0 ||
        sample.tv_sec > (INT64_MAX - 999) / 1000)
        return -1;
    return sample.tv_sec * 1000 + sample.tv_nsec / 1000000;
}
