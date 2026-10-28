// SPDX-License-Identifier: Apache-2.0
#include "qmutex_p.h"
#include <QtCore/qlogging.h>
#include <errno.h>
#include <time.h>
QT_BEGIN_NAMESPACE
static void check(int code, const char *operation)
{
    if (code) qFatal("QMutex XOS %s failed: %d", operation, code);
}
QMutexPrivate::QMutexPrivate() : xosCount(0)
{
    check(pthread_mutex_init(&xosMutex, nullptr), "mutex init");
    pthread_condattr_t attr;
    check(pthread_condattr_init(&attr), "condition attr init");
    check(pthread_condattr_setclock(&attr, CLOCK_MONOTONIC), "condition clock");
    check(pthread_cond_init(&xosCondition, &attr), "condition init");
    check(pthread_condattr_destroy(&attr), "condition attr destroy");
}
QMutexPrivate::~QMutexPrivate()
{
    check(pthread_cond_destroy(&xosCondition), "condition destroy");
    check(pthread_mutex_destroy(&xosMutex), "mutex destroy");
}
bool QMutexPrivate::wait(QDeadlineTimer deadline)
{
    check(pthread_mutex_lock(&xosMutex), "lock");
    while (!xosCount) {
        int result;
        if (deadline.isForever()) {
            result = pthread_cond_wait(&xosCondition, &xosMutex);
        } else {
            const qint64 ns = deadline.deadlineNSecs();
            timespec ts{time_t(ns / 1000000000), long(ns % 1000000000)};
            result = pthread_cond_timedwait(&xosCondition, &xosMutex, &ts);
        }
        if (result == ETIMEDOUT && !xosCount) {
            check(pthread_mutex_unlock(&xosMutex), "unlock");
            return false;
        }
        if (result && result != ETIMEDOUT) check(result, "wait");
    }
    --xosCount;
    check(pthread_mutex_unlock(&xosMutex), "unlock");
    return true;
}
void QMutexPrivate::wakeUp() noexcept
{
    check(pthread_mutex_lock(&xosMutex), "lock");
    ++xosCount;
    check(pthread_cond_signal(&xosCondition), "signal");
    check(pthread_mutex_unlock(&xosMutex), "unlock");
}
QT_END_NAMESPACE
