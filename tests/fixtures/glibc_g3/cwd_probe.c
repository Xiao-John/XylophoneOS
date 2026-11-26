/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(expression) do {                                          \
    if (!(expression)) {                                                \
        fprintf(stderr, "CWD_ACCESS_FAILURE line=%d errno=%d\n", __LINE__, errno); \
        return 1;                                                       \
    }                                                                   \
} while (0)

int main(int argc, char **argv)
{
    char cwd[256];
    CHECK(argc == 2);
    CHECK(getcwd(cwd, sizeof(cwd)) == cwd && strcmp(cwd, argv[1]) == 0);
    CHECK(getcwd(cwd, 0) == NULL && errno == EINVAL);
    CHECK(getcwd(cwd, 1) == NULL && errno == ERANGE && strcmp(cwd, argv[1]) == 0);
    CHECK(getcwd(NULL, 1) == NULL && errno == ERANGE);
    char *allocated = getcwd(NULL, 0);
    CHECK(allocated != NULL && strcmp(allocated, argv[1]) == 0);
    free(allocated);
    allocated = getcwd(NULL, 256);
    CHECK(allocated != NULL && strcmp(allocated, argv[1]) == 0);
    free(allocated);

    CHECK(chdir("/g3_cwd/sub/") == 0);
    CHECK(getcwd(cwd, sizeof(cwd)) == cwd && strcmp(cwd, "/g3_cwd/sub") == 0);
    CHECK(chdir(".././路") == 0);
    CHECK(getcwd(cwd, sizeof(cwd)) == cwd && strcmp(cwd, "/g3_cwd/路") == 0);
    CHECK(chdir("missing/../..") == -1 && errno == ENOENT);
    CHECK(chdir("../plain.txt/") == -1 && errno == ENOTDIR);
    CHECK(chdir("") == -1 && errno == ENOENT);
    CHECK(getcwd(cwd, sizeof(cwd)) == cwd && strcmp(cwd, "/g3_cwd/路") == 0);
    CHECK(chdir("..") == 0);
    int fd = open("plain.txt", O_RDONLY);
    CHECK(fd >= 0);
    char byte = '\0';
    CHECK(read(fd, &byte, 1) == 1 && byte == 'p');
    CHECK(faccessat(fd, "/g3_cwd/plain.txt", R_OK, 0) == 0);
    CHECK(faccessat(fd, "plain.txt", F_OK, 0) == -1 && errno == ENOTSUP);
    CHECK(close(fd) == 0);

    CHECK(faccessat(AT_FDCWD, "plain.txt", R_OK, AT_EACCESS | AT_SYMLINK_NOFOLLOW) == 0);
    CHECK(faccessat(AT_FDCWD, "read-only.txt", W_OK, AT_EACCESS) == -1 && errno == EACCES);
    CHECK(faccessat(AT_FDCWD, "plain.txt", F_OK, 0x8000) == -1 && errno == EINVAL);
    CHECK(faccessat(-1, "plain.txt", F_OK, 0) == -1 && errno == EBADF);
    CHECK(readlink("plain.txt", &byte, 1) == -1 && errno == EINVAL && byte == 'p');
    CHECK(readlink("missing", &byte, 1) == -1 && errno == ENOENT && byte == 'p');
    CHECK(readlink("plain.txt/x", &byte, 1) == -1 && errno == ENOTDIR && byte == 'p');
    char *canonical = realpath("sub/.././plain.txt", NULL);
    CHECK(canonical != NULL && strcmp(canonical, "/g3_cwd/plain.txt") == 0);
    free(canonical);
    canonical = canonicalize_file_name("/g3_cwd/路/../plain.txt");
    CHECK(canonical != NULL && strcmp(canonical, "/g3_cwd/plain.txt") == 0);
    free(canonical);
    CHECK(realpath("missing/../plain.txt", NULL) == NULL && errno == ENOENT);
    CHECK(realpath("plain.txt/", NULL) == NULL && errno == ENOTDIR);

    CHECK(access("plain.txt", F_OK) == 0);
    CHECK(access("plain.txt", R_OK | W_OK) == 0);
    CHECK(access("read-only.txt", F_OK | R_OK) == 0);
    CHECK(access("read-only.txt", W_OK) == -1 && errno == EACCES);
    CHECK(access("plain.txt", X_OK) == -1 && errno == EACCES);
    CHECK(access("/bin/g3_cwd", R_OK | X_OK) == 0);
    int writer = open("/bin/g3_cwd", O_RDWR);
    CHECK(writer >= 0 && lseek(writer, 1, SEEK_SET) == 1);
    CHECK(access("/bin/g3_cwd", W_OK | X_OK) == 0);
    CHECK(lseek(writer, 0, SEEK_CUR) == 1);
    CHECK(read(writer, &byte, 1) == 1 && byte == 'E');
    CHECK(pwrite(writer, &byte, 1, 1) == 1 && close(writer) == 0);
    int quota[32];
    size_t occupied = 0;
    while (occupied < sizeof(quota) / sizeof(quota[0])) {
        int opened = open("plain.txt", O_RDONLY);
        if (opened < 0) break;
        quota[occupied++] = opened;
    }
    CHECK(occupied != 0 && occupied < sizeof(quota) / sizeof(quota[0]) && errno == EMFILE);
    CHECK(access("/bin/g3_cwd", X_OK) == 0);
    CHECK(access("plain.txt", X_OK) == -1 && errno == EACCES);
    while (occupied != 0) {
        CHECK(close(quota[--occupied]) == 0);
    }
    CHECK(access("/bin/g3_cwd/", X_OK) == -1 && errno == ENOTDIR);
    CHECK(access(".", R_OK | W_OK | X_OK) == 0);
    CHECK(access("missing/../plain.txt", F_OK) == -1 && errno == ENOENT);
    CHECK(access("plain.txt/x", F_OK) == -1 && errno == ENOTDIR);
    CHECK(access("missing", 8) == -1 && errno == EINVAL);
    CHECK(access("", F_OK) == -1 && errno == ENOENT);
    CHECK(access("/dev/null", R_OK | W_OK) == 0);
    CHECK(access("/dev/null", X_OK) == -1 && errno == EACCES);
    CHECK(access("/dev/", R_OK | X_OK) == 0);
    CHECK(access("/dev/", W_OK) == -1 && errno == EACCES);
    CHECK(chdir("/") == 0);
    CHECK(getcwd(cwd, 2) == cwd && strcmp(cwd, "/") == 0);
    puts("GLIBC_CWD_ACCESS_PASS");
    return 0;
}
