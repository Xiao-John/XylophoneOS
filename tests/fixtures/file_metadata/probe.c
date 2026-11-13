/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
/* FAT metadata honest subset: RDO + mtime, chown no-op, ENOTSUP for the rest. */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <xos/file_client.hpp>

#ifndef UTIME_NOW
#define UTIME_NOW (-2L)
#endif
#ifndef UTIME_OMIT
#define UTIME_OMIT (-1L)
#endif

static int failures;

static void check(const char* name, bool ok) {
    printf("%s=%d\n", name, ok ? 1 : 0);
    if (!ok) { ++failures; }
}

int main(void) {
    const int fd = open("/meta.txt", O_CREAT | O_WRONLY | O_TRUNC, 0644);
    check("create", fd >= 0);
    if (fd < 0) { return 1; }
    check("write", write(fd, "x", 1) == 1);
    close(fd);

    struct stat status;
    memset(&status, 0, sizeof(status));
    check("stat_file", stat("/meta.txt", &status) == 0 && S_ISREG(status.st_mode)
                       && (status.st_mode & 07777) == 0644
                       && status.st_uid == 0 && status.st_gid == 0);

    check("chmod_readonly", chmod("/meta.txt", 0444) == 0);
    memset(&status, 0, sizeof(status));
    check("stat_readonly", stat("/meta.txt", &status) == 0
                           && (status.st_mode & 07777) == 0444);
    errno = 0;
    check("access_w_denied", access("/meta.txt", W_OK) == -1 && errno == EACCES);
    errno = 0;
    check("open_write_denied", open("/meta.txt", O_WRONLY) == -1 && errno == EACCES);

    check("chmod_writable", chmod("/meta.txt", 0644) == 0);
    check("access_w_ok", access("/meta.txt", W_OK) == 0);
    const int writable = open("/meta.txt", O_WRONLY);
    check("open_write_ok", writable >= 0);
    if (writable >= 0) { close(writable); }

    errno = 0;
    check("chmod_0600_notsup", chmod("/meta.txt", 0600) == -1 && errno == ENOTSUP);
    errno = 0;
    check("chmod_setuid_notsup", chmod("/meta.txt", 04755) == -1 && errno == ENOTSUP);
    check("chown_noop", chown("/meta.txt", (uid_t)-1, (gid_t)-1) == 0);
    errno = 0;
    check("chown_other_notsup", chown("/meta.txt", 1000, (gid_t)-1) == -1
                                && errno == ENOTSUP);

    struct timespec times[2];
    times[0].tv_sec = 0; times[0].tv_nsec = UTIME_OMIT;
    times[1].tv_sec = 1700000000; times[1].tv_nsec = 0;
    check("utimensat_mtime", utimensat(AT_FDCWD, "/meta.txt", times, 0) == 0);
    memset(&status, 0, sizeof(status));
    check("mtime_readback", stat("/meta.txt", &status) == 0 && status.st_mtime == 1700000000);

    times[0].tv_sec = 1700000000; times[0].tv_nsec = 0;
    times[1].tv_sec = 0; times[1].tv_nsec = UTIME_OMIT;
    errno = 0;
    check("explicit_atime_notsup", utimensat(AT_FDCWD, "/meta.txt", times, 0) == -1
                                   && errno == ENOTSUP);

    times[0].tv_sec = 0; times[0].tv_nsec = UTIME_OMIT;
    times[1].tv_sec = 0; times[1].tv_nsec = UTIME_OMIT;
    check("double_omit", utimensat(AT_FDCWD, "/meta.txt", times, 0) == 0);

    const int timed = open("/meta.txt", O_RDWR);
    times[0].tv_nsec = UTIME_OMIT;
    times[1].tv_sec = 1700000100; times[1].tv_nsec = 0;
    check("futimens_mtime", timed >= 0 && futimens(timed, times) == 0);
    memset(&status, 0, sizeof(status));
    check("fstat_mtime", timed >= 0 && fstat(timed, &status) == 0
                         && status.st_mtime == 1700000100);
    check("fchmod_readonly", timed >= 0 && fchmod(timed, 0444) == 0);
    memset(&status, 0, sizeof(status));
    check("fstat_readonly", timed >= 0 && fstat(timed, &status) == 0
                            && (status.st_mode & 07777) == 0444);
    check("fchmod_writable", timed >= 0 && fchmod(timed, 0644) == 0);
    if (timed >= 0) { close(timed); }

    // A writable handle already open must not bypass a later chmod(0444).
    const int before = open("/meta.txt", O_WRONLY);
    check("open_before_chmod", before >= 0);
    check("chmod_with_open_handle", chmod("/meta.txt", 0444) == 0);
    errno = 0;
    check("open_after_chmod_denied", open("/meta.txt", O_WRONLY) == -1 && errno == EACCES);
    // Path-form metadata writes must refresh an already-open object cache.
    struct stat handle_status;
    memset(&handle_status, 0, sizeof(handle_status));
    check("fstat_path_chmod_visible", before >= 0 && fstat(before, &handle_status) == 0
                                      && (handle_status.st_mode & 07777) == 0444);
    check("chmod_restore", chmod("/meta.txt", 0644) == 0);
    if (before >= 0) { close(before); }

    // Nanoseconds are validated before FAT quantization.
    times[0].tv_sec = 0; times[0].tv_nsec = UTIME_OMIT;
    times[1].tv_sec = 1700000100; times[1].tv_nsec = 1000000000;
    const int nano_fd = open("/meta.txt", O_RDWR);
    errno = 0;
    check("futimens_bad_nsec", nano_fd >= 0 && futimens(nano_fd, times) == -1 && errno == EINVAL);
    if (nano_fd >= 0) { close(nano_fd); }

    // RDO + MTIME in one request is rejected (no partial commit).
    xos::file::client raw;
    if (raw.init()) {
        const xos::i64 combined = raw.set_metadata(
            0, "/meta.txt",
            static_cast<xos::u16>(xos::file::metadata_read_only | xos::file::metadata_mtime),
            0, 0, 0, 1700000100, 0);
        check("combined_mask_rejected",
              combined == static_cast<xos::i64>(xos::file::status::not_supported));
    } else {
        check("combined_mask_rejected", false);
    }

    const int unlinked = open("/meta2.txt", O_CREAT | O_RDWR, 0644);
    check("create2", unlinked >= 0);
    check("unlink2", unlink("/meta2.txt") == 0);
    errno = 0;
    check("unlinked_fchmod_notsup", unlinked >= 0 && fchmod(unlinked, 0444) == -1
                                    && errno == ENOTSUP);
    if (unlinked >= 0) { close(unlinked); }

    check("mkdir", mkdir("/metadir", 0755) == 0);
    memset(&status, 0, sizeof(status));
    check("stat_dir", stat("/metadir", &status) == 0 && S_ISDIR(status.st_mode)
                      && (status.st_mode & 07777) == 0755);
    errno = 0;
    check("dbchmod_dir_notsup", chmod("/metadir", 0755) == -1 && errno == ENOTSUP);

    check("rmdir", rmdir("/metadir") == 0);
    check("cleanup", unlink("/meta.txt") == 0);
    printf("failures=%d\n", failures);
    puts(failures == 0 ? "FILE_METADATA_OK" : "FILE_METADATA_FAILED");
    return failures == 0 ? 0 : 1;
}
