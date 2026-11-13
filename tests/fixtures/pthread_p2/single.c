/* SPDX-License-Identifier: Apache-2.0 */
/* P2 subset in the ordinary (single-thread) SDK. */
#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdio.h>

int main(void) {
    sem_t sem;
    int value = -1;
    const int sem_ok = sem_init(&sem, 0, 2) == 0
        && sem_trywait(&sem) == 0
        && sem_getvalue(&sem, &value) == 0 && value == 1
        && sem_post(&sem) == 0
        && sem_wait(&sem) == 0
        && sem_getvalue(&sem, &value) == 0 && value == 1;

    pthread_barrier_t barrier;
    const int barrier_ok = pthread_barrier_init(&barrier, 0, 1) == 0
        && pthread_barrier_wait(&barrier) == PTHREAD_BARRIER_SERIAL_THREAD
        && pthread_barrier_destroy(&barrier) == 0;

    pthread_spinlock_t lock;
    const int spin_ok = pthread_spin_init(&lock, 0) == 0
        && pthread_spin_lock(&lock) == 0
        && pthread_spin_unlock(&lock) == 0
        && pthread_spin_trylock(&lock) == 0
        && pthread_spin_unlock(&lock) == 0
        && pthread_spin_destroy(&lock) == 0;

    size_t guard = 1;
    int shared = -1;
    pthread_condattr_t cond_attr;
    pthread_condattr_init(&cond_attr);
    pthread_rwlockattr_t rw_attr;
    int rw_shared = -1;
    const int attr_ok = pthread_attr_getguardsize(0, &guard) == 0 && guard == 0
        && pthread_condattr_getpshared(&cond_attr, &shared) == 0
        && shared == PTHREAD_PROCESS_PRIVATE
        && pthread_rwlockattr_init(&rw_attr) == 0
        && pthread_rwlockattr_getpshared(&rw_attr, &rw_shared) == 0
        && rw_shared == PTHREAD_PROCESS_PRIVATE
        && pthread_rwlockattr_destroy(&rw_attr) == 0;

    char name[16] = {0};
    const int name_ok = pthread_setname_np(pthread_self(), "main") == 0
        && pthread_getname_np(pthread_self(), name, sizeof(name)) == 0
        && name[0] == 'm';
    const int join_ok = pthread_tryjoin_np(pthread_self(), 0) == ENOTSUP;

    printf("sem=%d barrier=%d spin=%d attrs=%d name=%d join=%d value=%d\n",
           sem_ok, barrier_ok, spin_ok, attr_ok, name_ok, join_ok, value);
    const int ok = sem_ok && barrier_ok && spin_ok && attr_ok && name_ok && join_ok;
    puts(ok ? "PTHREAD_P2_SINGLE_OK" : "PTHREAD_P2_SINGLE_FAILED");
    return ok ? 0 : 1;
}
