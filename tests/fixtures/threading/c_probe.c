/* SPDX-License-Identifier: Apache-2.0 */
#define _POSIX_C_SOURCE 200809L
#include <pthread.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static __thread unsigned local = 9;
static void *worker(void *argument) {
    if (local != 9) _exit(97);
    local = 42; errno = 117;
    struct timespec duration = {0, 20000000};
    if (nanosleep(&duration, NULL) || local != 42 || errno != 117) _exit(98);
    return argument;
}
int main(void) {
    pthread_t id;
    void *value = NULL;
    if (pthread_create(&id, NULL, worker, (void *)(uintptr_t)47) ||
        pthread_equal(id, pthread_self()) || pthread_join(id, &value) ||
        value != (void *)(uintptr_t)47 || local != 9) return 99;
    puts("[cthread] C ABI TLS errno join=ok");
    return 0;
}
