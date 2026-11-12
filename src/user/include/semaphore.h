/* SPDX-License-Identifier: Apache-2.0 */
/* XOS semaphores: implemented on top of the pthread mutex/condition surface. */
#ifndef _XOS_SEMAPHORE_H
#define _XOS_SEMAPHORE_H

#include <pthread.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    unsigned value;
    int pshared;
    int initialized;
} sem_t;

#define SEM_FAILED ((sem_t*)0)

int sem_init(sem_t* sem, int pshared, unsigned value);
int sem_destroy(sem_t* sem);
int sem_wait(sem_t* sem);
int sem_trywait(sem_t* sem);
int sem_timedwait(sem_t* sem, const struct timespec* timeout);
int sem_post(sem_t* sem);
int sem_getvalue(sem_t* sem, int* value);

#ifdef __cplusplus
}
#endif

#endif
