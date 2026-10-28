// SPDX-License-Identifier: Apache-2.0
#include "qeventdispatcher_xos_p.h"
#include <QtCore/qcoreapplication.h>
#include <QtCore/qsocketnotifier.h>
#include <QtCore/qthread.h>
#include <private/qcoreapplication_p.h>
#include <private/qthread_p.h>
#include <limits>

QT_BEGIN_NAMESPACE
QEventDispatcherXos::QEventDispatcherXos(QObject *parent) : QAbstractEventDispatcherV2(parent) {}
QEventDispatcherXos::~QEventDispatcherXos() { timers.clearTimers(); }

bool QEventDispatcherXos::processEvents(QEventLoop::ProcessEventsFlags flags)
{
    __atomic_store_n(&interrupted, 0u, __ATOMIC_RELEASE);
    // Consume before inspecting the queue. A subsequent wake leaves the bit
    // set through the kernel compare, so the transition cannot be lost.
    const bool hadWake = gate.take();
    emit awake();
    auto *data = QThreadData::current();
    QCoreApplicationPrivate::sendPostedEvents(nullptr, 0, data);
    const bool includeTimers = !(flags & QEventLoop::X11ExcludeTimers);
    const bool mayWait = !hadWake && (flags & QEventLoop::WaitForMoreEvents) && data->canWaitLocked()
                         && !__atomic_load_n(&interrupted, __ATOMIC_ACQUIRE);
    if (mayWait) {
        emit aboutToBlock();
        xos::u64 deadline = xos::thread_deadline_infinite;
        if (includeTimers) {
            const auto remaining = timers.timerWait();
            if (remaining) {
                const xos::u64 now = xos::thread::clock();
                const auto count = remaining->count();
                const xos::u64 ns = count > 0 ? static_cast<xos::u64>(count) : 0;
                const auto limit = xos::thread_deadline_infinite - 1;
                deadline = ns > limit - now ? limit : now + ns;
            }
        }
        if (!__atomic_load_n(&interrupted, __ATOMIC_ACQUIRE)) {
            const auto result = gate.wait(deadline);
            if (result != 0 && result != xos::thread_value_changed && result != xos::thread_error_timeout)
                qFatal("QEventDispatcherXos: wait_word failed: %lld", static_cast<long long>(result));
        }
    }
    const int activated = includeTimers ? timers.activateTimers() : 0;
    return activated > 0 || hadWake || gate.pending();
}
void QEventDispatcherXos::registerSocketNotifier(QSocketNotifier *notifier)
{
    qWarning("QEventDispatcherXos: socket and FD notifiers are unsupported");
    notifier->setEnabled(false);
}
void QEventDispatcherXos::unregisterSocketNotifier(QSocketNotifier *) {}
void QEventDispatcherXos::registerTimer(Qt::TimerId id, Duration interval, Qt::TimerType type, QObject *object)
{
    if (qToUnderlying(id) < 1 || interval.count() < 0 || !object || object->thread() != thread() || thread() != QThread::currentThread()) {
        qWarning("QEventDispatcherXos: invalid timer registration or thread"); return;
    }
    timers.registerTimer(id, interval, type, object);
}
bool QEventDispatcherXos::unregisterTimer(Qt::TimerId id) { return timers.unregisterTimer(id); }
bool QEventDispatcherXos::unregisterTimers(QObject *object) { return object && timers.unregisterTimers(object); }
QList<QEventDispatcherXos::TimerInfoV2> QEventDispatcherXos::timersForObject(QObject *object) const { return object ? timers.registeredTimers(object) : QList<TimerInfoV2>{}; }
QEventDispatcherXos::Duration QEventDispatcherXos::remainingTime(Qt::TimerId id) const { return timers.remainingDuration(id); }
void QEventDispatcherXos::wakeUp() { if (gate.wake() < 0) qFatal("QEventDispatcherXos: wake_word failed"); }
void QEventDispatcherXos::interrupt() { __atomic_store_n(&interrupted, 1u, __ATOMIC_RELEASE); wakeUp(); }
QT_END_NAMESPACE
