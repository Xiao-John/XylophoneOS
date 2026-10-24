/* SPDX-License-Identifier: Apache-2.0 */
#include <fcntl.h>
#include <unistd.h>

int tls_worker_probe(int value);

static void xos_yield() {
    __asm__ volatile("int $0x80" : : "a"(3) : "memory");
}

int main(int argc, char** argv) {
    if (argc != 2 || argv[1][0] < '1' || argv[1][0] > '9' || argv[1][1] != '\0') return 2;
    const char own = argv[1][0];
    const char other = own == '4' ? '7' : '4';
    char own_path[] = "/tmp/tls_worker_0.ready";
    char other_path[] = "/tmp/tls_worker_0.ready";
    own_path[16] = own;
    other_path[16] = other;
    int descriptor = open(own_path, O_CREAT | O_TRUNC | O_WRONLY, 0600);
    if (descriptor < 0) return 3;
    if (write(descriptor, &own, 1) != 1 || close(descriptor) != 0) return 4;
    int found = 0;
    for (int i = 0; i < 1000000; ++i) {
        if (access(other_path, F_OK) == 0) { found = 1; break; }
        xos_yield();
    }
    if (!found) return 5;
    const int result = tls_worker_probe(own - '0') == 0 ? 0 : 6;
    unlink(own_path);
    return result;
}
