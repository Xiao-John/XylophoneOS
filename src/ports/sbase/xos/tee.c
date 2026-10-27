/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define MAX_OUTPUTS 31
static int write_all(int fd, const char *buffer, size_t length) {
    while (length) { ssize_t n = write(fd, buffer, length); if (n < 0 && errno == EINTR) continue; if (n <= 0) return -1; buffer += n; length -= (size_t)n; }
    return 0;
}
int main(int argc, char **argv) {
    int first=1, append=0, failed=0, fds[MAX_OUTPUTS], count=0;
    while (first < argc) {
        if (!strcmp(argv[first], "--")) { ++first; break; }
        if (argv[first][0] != '-' || !argv[first][1]) break;
        if (!strcmp(argv[first], "-a")) { append=1; ++first; continue; }
        fprintf(stderr, "tee: unsupported option: %s\n", argv[first]); return 2;
    }
    if (argc-first > MAX_OUTPUTS) { fprintf(stderr, "tee: too many files\n"); return 2; }
    for (int i=first;i<argc;++i) {
        int fd=open(argv[i], O_WRONLY|O_CREAT|(append ? O_APPEND : O_TRUNC), 0666);
        if (fd<0) { fprintf(stderr, "tee: %s: %s\n", argv[i], strerror(errno)); failed=1; }
        else fds[count++]=fd;
    }
    char buffer[4096]; ssize_t n; int stdout_ok = 1;
    for (;;) {
        n=read(0,buffer,sizeof(buffer));
        if (n<0 && errno==EINTR) continue;
        if (n<=0) break;
        if (stdout_ok && write_all(1,buffer,(size_t)n)) { perror("tee: stdout"); stdout_ok=0; failed=1; }
        for (int i=0;i<count;++i) if (fds[i]>=0 && write_all(fds[i],buffer,(size_t)n)) { perror("tee: write"); close(fds[i]); fds[i]=-1; failed=1; }
    }
    if (n<0) { perror("tee: read"); failed=1; }
    for (int i=0;i<count;++i) if (fds[i]>=0 && close(fds[i])) { perror("tee: close"); failed=1; }
    return failed;
}
