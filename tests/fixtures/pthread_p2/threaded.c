/* SPDX-License-Identifier: Apache-2.0 */
/* P2 pthread surface: semaphores, barrier, spinlock, names, attrs, thread join. */
#include <errno.h>
#include <pthread.h>
#include <semaphore.h>
#include <stdio.h>
#include <string.h>

static sem_t gate;
static pthread_barrier_t rendezvous;
static pthread_spinlock_t counter_lock;
static int counter;
static int serial_threads;

static void* worker(void* argument) {
    const long index = (long)argument;
    for (int i = 0; i < 500; ++i) {
        pthread_spin_lock(&counter_lock);
        ++counter;
        pthread_spin_unlock(&counter_lock);
    }
    sem_wait(&gate);
    sem_post(&gate);
    char name[16];
    if (pthread_getname_np(pthread_self(), name, sizeof(name)) == 0 && name[0] == '\0') {
        return (void*)1;
    }
    const int serial = pthread_barrier_wait(&rendezvous);
    if (serial == PTHREAD_BARRIER_SERIAL_THREAD) {
        __atomic_add_fetch(&serial_threads, 1, __ATOMIC_RELAXED);
    } else if (serial != 0) {
        return (void*)1;
    }
    return (void*)(index + 1);
}

int main(void) {
    sem_init(&gate, 0, 1);
    pthread_barrier_init(&rendezvous, 0, 2);
    pthread_spin_init(&counter_lock, 0);

    pthread_t first, second;
    const int first_created = pthread_create(&first, 0, worker, (void*)0);
    const int second_created = pthread_create(&second, 0, worker, (void*)1);
    const int created = first_created == 0 && second_created == 0;
    void* first_value = 0;
    void* second_value = 0;
    pthread_join(first, &first_value);
    pthread_join(second, &second_value);

    int sem_value = 0;
    sem_getvalue(&gate, &sem_value);
    sem_destroy(&gate);
    pthread_barrier_destroy(&rendezvous);
    pthread_spin_destroy(&counter_lock);

    size_t guard = 1;
    int guard_ok = pthread_attr_getguardsize(0, &guard) == 0 && guard == 0;
    pthread_condattr_t cond_attr;
    int shared = -1;
    pthread_condattr_init(&cond_attr);
    guard_ok = guard_ok && pthread_condattr_getpshared(&cond_attr, &shared) == 0
        && shared == PTHREAD_PROCESS_PRIVATE;
    pthread_condattr_destroy(&cond_attr);
    pthread_rwlockattr_t rw_attr;
    int rw_shared = -1;
    guard_ok = guard_ok && pthread_rwlockattr_init(&rw_attr) == 0
        && pthread_rwlockattr_getpshared(&rw_attr, &rw_shared) == 0
        && rw_shared == PTHREAD_PROCESS_PRIVATE
        && pthread_rwlockattr_destroy(&rw_attr) == 0;
    const int join_ok = pthread_tryjoin_np(first, 0) == ENOTSUP;
    clockid_t clock_id;
    const int clock_ok = pthread_getcpuclockid(first, &clock_id) == ENOTSUP;

    printf("created=%d counter=%d serial=%d sem=%d join=%d attrs=%d clock=%d\n",
           created, counter, serial_threads, sem_value, join_ok, guard_ok, clock_ok);
    const int ok = created && counter == 1000 && serial_threads == 1 && sem_value == 1
        && join_ok && guard_ok && clock_ok
        && first_value != 0 && second_value != 0;
    puts(ok ? "PTHREAD_P2_OK" : "PTHREAD_P2_FAILED");
    return ok ? 0 : 1;
}
