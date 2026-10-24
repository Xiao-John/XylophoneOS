/* SPDX-License-Identifier: Apache-2.0 */
#include <cstdio>

namespace {
struct task_lifetime {
    int value = 42;
    ~task_lifetime() {
        FILE* marker = std::fopen("/out/cpp_tls_destructor.marker", "wb");
        if (marker) {
            std::fputs(value == 42 ? "tls_destructed\n" : "bad\n", marker);
            std::fclose(marker);
        }
    }
};
thread_local task_lifetime lifetime;
}

thread_local int task_local_value = 0;

static unsigned long xos_ticks() {
    unsigned long result;
    __asm__ volatile("int $0x80" : "=a"(result) : "0"(7) : "memory");
    return result;
}

static void xos_yield() {
    __asm__ volatile("int $0x80" : : "a"(3) : "memory");
}

int tls_probe() {
    if (task_local_value != 0 || lifetime.value != 42) return -1;
    task_local_value = 19;
    return task_local_value == 19 ? 0 : -1;
}

int tls_worker_probe(int value) {
    if (task_local_value != 0) return -1;
    task_local_value = value;
    for (int i = 0; i < 8; ++i) {
        const unsigned long tick = xos_ticks();
        while (xos_ticks() == tick) {
            xos_yield();
            if (task_local_value != value) return -1;
        }
        if (task_local_value != value) return -1;
    }
    for (int i = 0; i < 2048; ++i) {
        xos_yield();
        if (task_local_value != value) return -1;
    }
    return 0;
}
