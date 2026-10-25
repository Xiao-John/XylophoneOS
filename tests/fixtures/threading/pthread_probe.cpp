// SPDX-License-Identifier: Apache-2.0
#include <pthread.h>
#include <xos/thread_core.hpp>
#include <stdlib.h>
#include <stdio.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <sys/stat.h>
#include <dirent.h>
using namespace xos;
extern "C" void* _sbrk(ptrdiff_t);
namespace {
pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
pthread_cond_t cond = PTHREAD_COND_INITIALIZER;
pthread_once_t once = PTHREAD_ONCE_INIT;
pthread_key_t key;
unsigned once_count, produced, consumed, slot, tls_destructors, tss_destructors;
unsigned exit_callbacks;
__thread unsigned tls_number = 17;
__thread unsigned local_round;
__thread unsigned tls_clean;
void check(bool good, const char* label) {
    if (!good) { printf("[pthread] FAIL %s errno=%d\n", label, errno); _exit(91); }
}
void once_init() { ++once_count; }
void tls_destroy(void*) { tls_clean = 1; __atomic_fetch_add(&tls_destructors, 1u, __ATOMIC_RELAXED); }
extern "C" int __cxa_thread_atexit(void(*)(void*), void*, void*);
void tss_destroy(void* value) {
    check(tls_clean == 1, "TLS-before-TSS");
    ++local_round; __atomic_fetch_add(&tss_destructors, 1u, __ATOMIC_RELAXED);
    if (local_round < 5) { check(pthread_setspecific(key, value) == 0, "TSS-reset"); }
}
void* worker(void* raw) {
    const unsigned index = static_cast<unsigned>(reinterpret_cast<uintptr_t>(raw));
    check(tls_number == 17, "TLS-init"); tls_number = index + 100;
    errno = static_cast<int>(201 + index);
    thread::sleep_until(thread::clock() + 20000000);
    check(errno == static_cast<int>(201 + index) && tls_number == index + 100, "errno-TLS-isolation");
    char tokens[8]; snprintf(tokens, sizeof(tokens), "%u:b:c", index);
    check(strtok(tokens, ":") == tokens, "strtok-first");
    thread::sleep_until(thread::clock() + 20000000);
    check(strtok(nullptr, ":") == tokens + 2, "strtok-reent");
    check(__cxa_thread_atexit(tls_destroy, nullptr, nullptr) == 0, "TLS-register");
    check(pthread_setspecific(key, reinterpret_cast<void*>(1)) == 0, "TSS-set");
    pthread_attr_t actual; void* stack; size_t size;
    check(pthread_getattr_np(pthread_self(), &actual) == 0 && pthread_attr_getstack(&actual, &stack, &size) == 0 && size == thread_stack_default,
          "stack-query");
    for (unsigned i = 0; i < 150; ++i) {
        check(pthread_once(&once, once_init) == 0, "once");
        auto* data = static_cast<unsigned char*>(malloc(64 + i)); check(data != nullptr, "malloc");
        memset(data, static_cast<int>(index + 1), 64 + i);
        auto* grown = static_cast<unsigned char*>(realloc(data, 256 + i)); check(grown && grown[0] == index + 1, "realloc");
        free(grown);
    }
    char path[40]; snprintf(path, sizeof(path), "/thread%u.txt", index);
    for (unsigned i = 0; i < 4; ++i) {
        const int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, 0600); check(fd >= 0, "open");
        const int copy = dup(fd); check(copy >= 0, "dup");
        char text[32]; const int n = snprintf(text, sizeof(text), "thread=%u pass=%u\n", index, i);
        check(write(fd, text, static_cast<size_t>(n)) == n, "file-write");
        check(lseek(copy, 0, SEEK_SET) == 0, "shared-seek");
        char input[32]{}; check(read(fd, input, static_cast<size_t>(n)) == n && memcmp(input, text, static_cast<size_t>(n)) == 0, "shared-offset-read");
        check(close(fd) == 0 && close(copy) == 0, "close");
    }
    char envname[24]; snprintf(envname, sizeof(envname), "THREAD_ENV_%u", index);
    for (unsigned i = 0; i < 20; ++i) { check(setenv(envname, "present", 1) == 0, "concurrent-setenv"); }
    DIR* directory = opendir("/"); check(directory != nullptr, "opendir");
    check(readdir(directory) != nullptr && closedir(directory) == 0, "directory-lifetime");
    for (unsigned i = 0; i < 16; ++i) {
        pthread_mutex_lock(&mutex);
        if (index == 0) {
            while (slot) { check(pthread_cond_wait(&cond, &mutex) == 0, "producer-cond"); }
            slot = i + 1; ++produced;
        } else {
            while (!slot) { check(pthread_cond_wait(&cond, &mutex) == 0, "consumer-cond"); }
            check(slot == i + 1, "predicate"); slot = 0; ++consumed;
        }
        pthread_cond_broadcast(&cond); pthread_mutex_unlock(&mutex);
    }
    printf("[pthread] worker=%u done\n", index);
    if (index == 1) { pthread_exit(reinterpret_cast<void*>(42)); }
    return reinterpret_cast<void*>(41);
}
void exit_callback() { ++exit_callbacks; printf("[pthread] process-fini=%u\n", exit_callbacks); }
void* stream_creator(void*) {
    FILE* stream = fopen("/thread_stream.txt", "w+"); check(stream != nullptr, "stream-create");
    check(fputs("cross-thread-stream\n", stream) >= 0 && fflush(stream) == 0, "stream-write");
    rewind(stream); return stream;
}
void recursive_exit(void*) { exit(23); }
void* recursive_worker(void*) {
    check(__cxa_thread_atexit(recursive_exit, nullptr, nullptr) == 0, "recursive-register"); return nullptr;
}
void* final_worker(void*) {
    thread::sleep_until(thread::clock() + 30000000); return nullptr;
}
void* infinite(void*) { for (;;) { __asm__ volatile("" : : : "memory"); } }
}
int main(int argc, char** argv, char**) {
    check(atexit(exit_callback) == 0, "atexit");
    if (argc > 1 && strcmp(argv[1], "recursive") == 0) {
        pthread_t id; check(pthread_create(&id, nullptr, recursive_worker, nullptr) == 0, "recursive-create");
        pthread_join(id, nullptr); _exit(94);
    }
    if (argc > 1 && strcmp(argv[1], "last") == 0) {
        pthread_t id; check(pthread_create(&id, nullptr, final_worker, nullptr) == 0, "last-create");
        pthread_exit(nullptr);
    }
    if (argc > 1 && (strcmp(argv[1], "exit") == 0 || strcmp(argv[1], "quick") == 0)) {
        pthread_t id; check(pthread_create(&id, nullptr, infinite, nullptr) == 0, "exit-create");
        thread::sleep_until(thread::clock() + 20000000);
        if (strcmp(argv[1], "quick") == 0) { _exit(19); }
        exit(9);
    }
    check(_sbrk(INTPTR_MAX) == reinterpret_cast<void*>(-1) && errno == ENOMEM, "sbrk-overflow-rejected");
    pthread_attr_t attr; check(pthread_attr_init(&attr) == 0, "attr-init");
    check(pthread_attr_setstacksize(&attr, 1) == EINVAL, "invalid-stack");
    check(pthread_attr_setstack(&attr, reinterpret_cast<void*>(0x70000000), 65536) == ENOTSUP, "caller-stack-denied");
    pthread_mutexattr_t ma; pthread_mutexattr_init(&ma);
    check(pthread_mutexattr_setpshared(&ma, PTHREAD_PROCESS_SHARED) == ENOTSUP, "process-shared-denied");
    pthread_mutexattr_settype(&ma, PTHREAD_MUTEX_ERRORCHECK); pthread_mutex_t checked;
    check(pthread_mutex_init(&checked, &ma) == 0 && pthread_mutex_lock(&checked) == 0, "errorcheck-init");
    check(pthread_mutex_lock(&checked) == EDEADLK && pthread_mutex_trylock(&checked) == EBUSY, "errorcheck-self");
    check(pthread_mutex_destroy(&checked) == EBUSY, "busy-mutex-destroy");
    check(pthread_mutex_unlock(&checked) == 0 && pthread_mutex_unlock(&checked) == EPERM && pthread_mutex_destroy(&checked) == 0, "mutex-owner");
    pthread_mutexattr_settype(&ma, PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(&checked, &ma); pthread_mutex_lock(&checked); pthread_mutex_lock(&checked);
    check(pthread_mutex_unlock(&checked) == 0 && pthread_mutex_unlock(&checked) == 0, "recursive");
    pthread_mutex_destroy(&checked);
    check(pthread_key_create(&key, tss_destroy) == 0, "key-create");
    pthread_t ids[2];
    for (unsigned i = 0; i < 2; ++i) { check(pthread_create(&ids[i], nullptr, worker, reinterpret_cast<void*>(static_cast<uintptr_t>(i))) == 0, "create"); }
    for (unsigned i = 0; i < 2; ++i) { void* value; check(pthread_join(ids[i], &value) == 0 && value == reinterpret_cast<void*>(static_cast<uintptr_t>(41 + i)), "join-value"); }
    check(getenv("THREAD_ENV_0") && getenv("THREAD_ENV_1") && strcmp(getenv("THREAD_ENV_0"), "present") == 0 && strcmp(getenv("THREAD_ENV_1"), "present") == 0, "environment-shared");
    check(once_count == 1 && produced == 16 && consumed == 16 && slot == 0, "once-producer-consumer");
    check(tls_destructors == 2 && tss_destructors == 8 && tls_number == 17, "destructor-four-rounds");
    check(pthread_key_delete(key) == 0 && pthread_setspecific(key, nullptr) == EINVAL, "deleted-key");
    pthread_t stream_thread; void* stream_value;
    check(pthread_create(&stream_thread, nullptr, stream_creator, nullptr) == 0 && pthread_join(stream_thread, &stream_value) == 0,
          "stream-creator-exit");
    FILE* stream = static_cast<FILE*>(stream_value); char line[64];
    check(fgets(line, sizeof(line), stream) && strcmp(line, "cross-thread-stream\n") == 0 && fclose(stream) == 0,
          "FILE-survives-creator-thread");
    pthread_mutex_lock(&mutex); timespec ts{0,0};
    check(pthread_cond_timedwait(&cond, &mutex, &ts) == ENOTSUP, "realtime-not-faked");
    pthread_mutex_unlock(&mutex);
    pthread_condattr_t ca; pthread_condattr_init(&ca); pthread_condattr_setclock(&ca, CLOCK_MONOTONIC);
    pthread_cond_t timed; pthread_cond_init(&timed, &ca);
    const u64 until = thread::clock() + 15000000;
    ts = {static_cast<time_t>(until / 1000000000), static_cast<long>(until % 1000000000)};
    pthread_mutex_lock(&mutex);
    check(pthread_cond_timedwait(&timed, &mutex, &ts) == ETIMEDOUT && thread::clock() >= until, "monotonic-cond-timeout");
    check(pthread_mutex_unlock(&mutex) == 0, "timeout-reacquires-mutex");
    pthread_cond_destroy(&timed);
    thread_stats status{}; sdk::syscall(sys_thread_stats, reinterpret_cast<u64>(&status));
    check(status.threads == 1 && status.reserved == 0 && status.results == 0, "thread-slots-reclaimed");
    printf("[pthread] mutex cond once TSS errno TLS malloc stdio files lifecycle=ok\n");
    return 0;
}
