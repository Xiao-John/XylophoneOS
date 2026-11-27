#include <stdio.h>
#include <string.h>
#include "xos_file_session.h"

enum { page_bytes = 4096, pages = 48, requests = pages * 2, rounds = 3 };
static struct {
    unsigned int mode, sample, chunk, receives_empty, sleep_attempts, bytes;
    unsigned long long offset;
    long before, after;
} readings[rounds * requests];
static struct {
    long start, finish;
    unsigned int empty, sleeps, bytes, digest;
} phases[rounds];
static int yield_for_sleep;
static unsigned int empty_receives, sleep_attempts;

static long trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
    long result;
    __asm__ volatile ("int $0x80" : "=a" (result)
                      : "a" (number), "D" (first), "S" (second), "d" (third)
                      : "memory", "cc");
    return result;
}

long __xos_file_test_trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third)
{
    if (number == 47) {
        ++sleep_attempts;
        if (yield_for_sleep) {
            (void) trap(3, 0, 0, 0);
            return 0;
        }
    }
    long result = trap(number, first, second, third);
    if (number == 5 && result == -3)
        ++empty_receives;
    return result;
}

static struct xos_file_request request;
static struct xos_file_response response;

int main(void)
{
    struct xos_file_session session = {0};
    request.operation = file_open;
    request.flags = 1U | (1U << 11); /* read-only pin */
    const char path[] = "/bin/quick.elf";
    memcpy(request.name, path, sizeof(path));
    request.name_length = sizeof(path) - 1;
    long result = __xos_file_session_call(&session, &request, &response);
    if (result != 0) {
        printf("TIMING_OPEN_FAILED %ld\n", result);
        return 1;
    }
    const unsigned int handle = response.handle;
    const long tick_ns = trap(46, 1, 0, 0);
    for (unsigned int phase = 0; phase < rounds; ++phase) {
        yield_for_sleep = phase == 1;
        phases[phase].start = trap(46, 0, 0, 0);
        for (unsigned int page = 0; page < pages; ++page) {
            const unsigned int maximum = sizeof(response.data);
            for (unsigned int chunk = 0; chunk < 2; ++chunk) {
                memset(&request, 0, sizeof(request));
                request.operation = 30; /* read_at */
                request.handle = handle;
                request.length = chunk == 0 ? maximum : page_bytes - maximum;
                request.offset = (page + 2048ULL) * page_bytes + (chunk == 0 ? 0 : maximum);
                const unsigned int sample = 2 * page + chunk;
                const unsigned int slot = phase * requests + sample;
                empty_receives = sleep_attempts = 0;
                readings[slot].before = trap(46, 0, 0, 0);
                result = __xos_file_session_call(&session, &request, &response);
                readings[slot].after = trap(46, 0, 0, 0);
                if (result != 0 || response.length != request.length) {
                    printf("TIMING_READ_FAILED phase=%u sample=%u status=%ld bytes=%u\n",
                           phase, sample, result, response.length);
                    return 2;
                }
                readings[slot].mode = phase;
                readings[slot].sample = sample;
                readings[slot].chunk = chunk;
                readings[slot].offset = request.offset;
                readings[slot].bytes = response.length;
                readings[slot].receives_empty = empty_receives;
                readings[slot].sleep_attempts = sleep_attempts;
                phases[phase].empty += empty_receives;
                phases[phase].sleeps += sleep_attempts;
                phases[phase].bytes += response.length;
                for (unsigned int byte = 0; byte < response.length; ++byte)
                    phases[phase].digest = (phases[phase].digest * 33U) ^ response.data[byte];
            }
        }
        phases[phase].finish = trap(46, 0, 0, 0);
    }
    yield_for_sleep = 0;
    memset(&request, 0, sizeof(request));
    request.operation = 8; /* close */
    request.handle = handle;
    if (__xos_file_session_call(&session, &request, &response) != 0)
        return 3;
    printf("TIMING_TICK_NS %ld\n", tick_ns);
    for (unsigned int sample = 0; sample < rounds * requests; ++sample)
        printf("TIMING_READ %u %u %u %llu %u %ld %ld %u %u\n", readings[sample].mode,
               readings[sample].sample, readings[sample].chunk, readings[sample].offset,
               readings[sample].bytes, readings[sample].before, readings[sample].after,
               readings[sample].receives_empty, readings[sample].sleep_attempts);
    for (unsigned int phase = 0; phase < rounds; ++phase)
        printf("TIMING_PHASE %u %ld %ld %u %u %u %08x\n", phase, phases[phase].start,
               phases[phase].finish, phases[phase].bytes, phases[phase].empty,
               phases[phase].sleeps, phases[phase].digest);
    if (phases[0].digest != phases[1].digest || phases[0].digest != phases[2].digest)
        return 4;
    puts("FILE_EXCHANGE_TIMING_OK");
    return 0;
}
