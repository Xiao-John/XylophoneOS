/* SPDX-License-Identifier: Apache-2.0 */
#include <stdint.h>
#include <unistd.h>
#include <sys/wait.h>

struct xos_tty_marker { uint64_t magic; uint32_t version, size; };
__attribute__((section(".xos.tty"), used)) static const struct xos_tty_marker marker = {
    0x31595454534f5858ULL, 1, sizeof(struct xos_tty_marker)
};

int main(void) {
    int release[2];
    if (pipe(release) != 0) return 3;
    const pid_t child = fork();
    if (child == 0) {
        char byte;
        if (read(release[0], &byte, 1) != 1 || byte != 'g') _exit(4);
        _exit(read(0, &byte, 1) < 0 ? 0 : 5);
    }
    if (child < 0) return 6;
    const char ready[] = "W1_FAULT_APP_READY\n";
    for (unsigned i = 0; i < sizeof(ready) - 1; ++i)
        if (write(1, ready + i, 1) != 1) return 1;
    const char go = 'g';
    if (write(release[1], &go, 1) != 1) return 7;
    int status = 0;
    if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 8;
    char byte;
    return read(0, &byte, 1) < 0 ? 0 : 2;
}
