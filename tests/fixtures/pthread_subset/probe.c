/* SPDX-License-Identifier: Apache-2.0 */
/* Single-thread pthread subset: once, TSS, mutex, cond, rwlock, identity, create. */
#include <errno.h>
#include <pthread.h>
#include <stdio.h>

static pthread_once_t once_control = PTHREAD_ONCE_INIT;
static int once_runs;

static void once_body(void) { ++once_runs; }

int main(void) {
    pthread_once(&once_control, once_body);
    pthread_once(&once_control, once_body);

    pthread_key_t key;
    void* value = 0;
    const int key_ok = pthread_key_create(&key, 0) == 0
        && pthread_setspecific(key, (void*)0x1234) == 0
        && (value = pthread_getspecific(key)) == (void*)0x1234
        && pthread_key_delete(key) == 0;

    pthread_mutex_t mutex;
    pthread_mutexattr_t mutex_attr;
    pthread_mutexattr_init(&mutex_attr);
    pthread_mutexattr_settype(&mutex_attr, PTHREAD_MUTEX_RECURSIVE);
    const int mutex_ok = pthread_mutex_init(&mutex, &mutex_attr) == 0
        && pthread_mutex_lock(&mutex) == 0
        && pthread_mutex_unlock(&mutex) == 0;

    pthread_cond_t cond;
    pthread_condattr_t cond_attr;
    pthread_condattr_init(&cond_attr);
    const int cond_ok = pthread_cond_init(&cond, &cond_attr) == 0
        && pthread_cond_signal(&cond) == 0
        && pthread_cond_wait(&cond, &mutex) == 0      /* spurious wakeup is legal */
        && pthread_cond_destroy(&cond) == 0;

    const int mutex_done = pthread_mutex_destroy(&mutex) == 0
        && pthread_mutexattr_destroy(&mutex_attr) == 0;

    pthread_rwlock_t rwlock;
    const int rwlock_ok = pthread_rwlock_init(&rwlock, 0) == 0
        && pthread_rwlock_rdlock(&rwlock) == 0
        && pthread_rwlock_unlock(&rwlock) == 0
        && pthread_rwlock_wrlock(&rwlock) == 0
        && pthread_rwlock_unlock(&rwlock) == 0
        && pthread_rwlock_destroy(&rwlock) == 0;

    const int identity_ok = pthread_equal(pthread_self(), pthread_self())
        && sched_yield() == 0;

    pthread_t thread;
    errno = 0;
    const int create = pthread_create(&thread, 0, 0, 0);
    const int create_errno = errno;
    const int create_ok = create == ENOSYS && create_errno == ENOSYS;

    printf("once=%d key=%d mutex=%d cond=%d rwlock=%d id=%d create=%d/%d\n",
           once_runs, key_ok, mutex_ok, cond_ok, rwlock_ok, identity_ok,
           create, create_errno);
    const int ok = once_runs == 1 && key_ok && mutex_ok && mutex_done && cond_ok
        && rwlock_ok && identity_ok && create_ok;
    puts(ok ? "PTHREAD_SUBSET_OK" : "PTHREAD_SUBSET_FAILED");
    return ok ? 0 : 1;
}
