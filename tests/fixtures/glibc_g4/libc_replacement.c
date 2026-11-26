/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>

int main(void)
{
    const char *present = "/state/regular.txt";
    char target[32];

    errno = 0;
    const int access_result = faccessat(AT_FDCWD, present, F_OK, 0);
    const int access_error = errno;
    errno = 0;
    const ssize_t link_result = readlink(present, target, sizeof(target));
    const int link_error = errno;
    errno = 0;
    const ssize_t missing_result = readlink("/state/missing.txt", target, sizeof(target));
    const int missing_error = errno;

    printf("RELINK_PATH_RESULT access=%d/%d regular=%ld/%d missing=%ld/%d\n",
           access_result, access_error, (long)link_result, link_error,
           (long)missing_result, missing_error);
    if (access_result == -1 && access_error == ENOSYS && link_result == -1 &&
        link_error == ENOSYS && missing_result == -1 && missing_error == ENOSYS) {
        puts("STATIC_RELINK_BASE_STUBS");
        return 0;
    }
    if (access_result == 0 && link_result == -1 && link_error == EINVAL &&
        missing_result == -1 && missing_error == ENOENT) {
        puts("STATIC_RELINK_REPLACEMENT_PATH_API");
        return 0;
    }
    return 1;
}
