// SPDX-License-Identifier: Apache-2.0
#ifndef QEVENTDISPATCHER_XOS_P_H
#define QEVENTDISPATCHER_XOS_P_H
// Private implementation detail, not a public Qt API. We mean it.
#include <QtCore/qabstracteventdispatcher.h>
#include <private/qtimerinfo_unix_p.h>
#include "wake_gate.hpp"

QT_BEGIN_NAMESPACE
class QEventDispatcherXos final : public QAbstractEventDispatcherV2 {
public:
    explicit QEventDispatcherXos(QObject *parent = nullptr);
    ~QEventDispatcherXos() override;
    bool processEvents(QEventLoop::ProcessEventsFlags flags) override;
    void registerSocketNotifier(QSocketNotifier *notifier) override;
    void unregisterSocketNotifier(QSocketNotifier *notifier) override;
    void registerTimer(Qt::TimerId id, Duration interval, Qt::TimerType type, QObject *object) override;
    bool unregisterTimer(Qt::TimerId id) override;
    bool unregisterTimers(QObject *object) override;
    QList<TimerInfoV2> timersForObject(QObject *object) const override;
    Duration remainingTime(Qt::TimerId id) const override;
    void wakeUp() override;
    void interrupt() override;
private:
    xos_wake_gate gate;
    QTimerInfoList timers;
    unsigned interrupted = 0;
};
QT_END_NAMESPACE

#endif
