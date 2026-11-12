/* SPDX-License-Identifier: Apache-2.0 */
/* Ordinary SDK guest probe: an intermediate parent exits before its COW child
   writes memory. Run in a fork-authorized process; a host run is not evidence. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
    int lifetime[2], report[2];
    if (pipe(lifetime) || pipe(report)) return 1;
    unsigned char* memory = mmap(NULL, 8192, PROT_READ | PROT_WRITE,
                                 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (memory == MAP_FAILED) return 2;
    memory[0] = 17; memory[4096] = 23;
    const pid_t parent = fork();
    if (parent < 0) return 3;
    if (parent == 0) {
        close(report[0]);
        const pid_t child = fork();
        if (child < 0) _exit(4);
        if (child != 0) _exit(0);
        close(lifetime[1]);
        char byte;
        if (read(lifetime[0], &byte, 1) != 0) _exit(5);
        close(lifetime[0]);
        memory[0] = 31;
        memory[4096] = 37;
        const unsigned char result[2] = {memory[0], memory[4096]};
        if (write(report[1], result, sizeof(result)) != (ssize_t)sizeof(result)) _exit(6);
        close(report[1]);
        if (munmap(memory, 8192) != 0) _exit(7);
        _exit(0);
    }
    close(lifetime[0]); close(lifetime[1]); close(report[1]);
    int status = 0;
    if (waitpid(parent, &status, 0) != parent || !WIFEXITED(status) || WEXITSTATUS(status)) return 8;
    unsigned char result[2];
    if (read(report[0], result, sizeof(result)) != (ssize_t)sizeof(result) ||
        result[0] != 31 || result[1] != 37 || memory[0] != 17 || memory[4096] != 23) return 9;
    char byte;
    if (read(report[0], &byte, 1) != 0 || close(report[0]) || munmap(memory, 8192)) return 10;
    puts("[cow2-runtime] parent_exit_child_write=PASS");
    return 0;
}
