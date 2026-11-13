/* SPDX-License-Identifier: Apache-2.0 */
/* /dev/null: writes are discarded, reads hit EOF, size stays zero. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(void) {
    char buffer[8] = {0};
    errno = 0;
    const int fd = open("/dev/null", O_RDWR);
    const int open_errno = errno;
    ssize_t written = -1;
    ssize_t read_back = -1;
    off_t offset = -1;
    if (fd >= 0) {
        written = write(fd, "abcde", 5);
        offset = lseek(fd, 0, SEEK_SET);
        read_back = read(fd, buffer, sizeof(buffer));
    }
    struct stat dev_status;
    memset(&dev_status, 0, sizeof(dev_status));
    errno = 0;
    const int dev_stat = stat("/dev", &dev_status);
    const int dev_errno = errno;
    struct stat status;
    memset(&status, 0, sizeof(status));
    const int stat_ok = stat("/dev/null", &status) == 0 && status.st_size == 0;
    struct stat handle_status;
    memset(&handle_status, 0, sizeof(handle_status));
    const int fstat_ok = fstat(fd, &handle_status) == 0 && handle_status.st_size == 0;
    errno = 0;
    const int missing = open("/dev/not-null", O_RDONLY);
    const int missing_errno = errno;
    errno = 0;
    const int exclusive = open("/dev/null", O_CREAT | O_EXCL | O_RDWR);
    const int exclusive_errno = errno;
    const int closed = fd >= 0 ? close(fd) : -1;

    printf("excl=%d/%d dev_stat=%d/%d dev_mode=%o ", exclusive, exclusive_errno,
           dev_stat, dev_errno, (unsigned)dev_status.st_mode);
    printf("fd=%d open_errno=%d write=%ld offset=%ld read=%ld stat=%d fstat=%d close=%d missing=%d/%d\n",
           fd, open_errno, (long)written, (long)offset, (long)read_back, stat_ok, fstat_ok, closed,
           missing, missing_errno);
    const int ok = fd >= 0 && written == 5 && offset == 0 && read_back == 0
        && stat_ok && fstat_ok && closed == 0
        && missing == -1 && missing_errno == ENOENT
        && exclusive == -1 && exclusive_errno == EEXIST;
    puts(ok ? "DEV_NULL_OK" : "DEV_NULL_FAILED");
    return ok ? 0 : 1;
}
