/* SPDX-License-Identifier: Apache-2.0 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* This target uses the G3 startup file receiver. */
__attribute__((used, section(".xos.exec")))
static const struct { unsigned long long magic; unsigned int version, size; }
receiver = { 0x3349424143455858ULL, 3, 16 };

enum { payload_size = 10037 };

static unsigned char pattern(size_t position)
{
    return (unsigned char) (position % 251);
}

static int write_all(int fd, const void *data, size_t length)
{
    const unsigned char *bytes = data;
    while (length != 0) {
        ssize_t count = write(fd, bytes, length);
        if (count <= 0) return -1;
        bytes += count;
        length -= (size_t) count;
    }
    return 0;
}

static int emit(int expected_status, int reader_closes)
{
    unsigned char bytes[payload_size];
    for (size_t i = 0; i < sizeof(bytes); ++i) bytes[i] = pattern(i);
    if (write_all(STDOUT_FILENO, bytes, sizeof(bytes)) != 0)
        return reader_closes && errno == EPIPE ? 0 : 80;
    return reader_closes ? 81 : expected_status;
}

static int receive(int relay)
{
    size_t position = 0;
    for (;;) {
        unsigned char bytes[997];
        ssize_t count = read(STDIN_FILENO, bytes, sizeof(bytes));
        if (count < 0) return 82;
        if (count == 0) break;
        for (ssize_t i = 0; i < count; ++i) {
            if (position >= payload_size || bytes[i] != pattern(position++)) return 83;
        }
        if (relay && write_all(STDOUT_FILENO, bytes, (size_t) count) != 0) return 84;
    }
    if (position != payload_size) return 85;
    if (!relay) puts("DASH_GLIBC_STREAM_BYTES=10037");
    return 0;
}

static int line(void)
{
    char input[64];
    if (fgets(input, sizeof(input), stdin) != input || fgetc(stdin) != EOF || ferror(stdin))
        return 86;
    if (write_all(STDOUT_FILENO, input, strlen(input)) != 0 ||
        write_all(STDERR_FILENO, "stream stderr\n", 14) != 0) return 87;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 2) return 90;
    for (int fd = 3; fd < 32; ++fd)
        if (fcntl(fd, F_GETFD) != -1 || errno != EBADF) return 91;
    if (strcmp(argv[1], "emit") == 0) return emit(0, 0);
    if (strcmp(argv[1], "emit7") == 0) return emit(7, 0);
    if (strcmp(argv[1], "emit-close") == 0) return emit(0, 1);
    if (strcmp(argv[1], "relay") == 0) return receive(1);
    if (strcmp(argv[1], "verify") == 0) return receive(0);
    if (strcmp(argv[1], "line") == 0) return line();
    if (strcmp(argv[1], "one") == 0) {
        unsigned char byte;
        return read(STDIN_FILENO, &byte, 1) == 1 && byte == pattern(0) ? 0 : 88;
    }
    if (strcmp(argv[1], "closed-out") == 0)
        return fcntl(STDOUT_FILENO, F_GETFD) == -1 && errno == EBADF ? 0 : 89;
    if (strcmp(argv[1], "closed-err") == 0)
        return fcntl(STDERR_FILENO, F_GETFD) == -1 && errno == EBADF ? 0 : 89;
    return 92;
}
