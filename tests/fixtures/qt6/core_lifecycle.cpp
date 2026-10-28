// SPDX-License-Identifier: Apache-2.0
// Exercise the check-to-block boundary and normal worker dispatcher teardown.
#include <QAbstractEventDispatcher>
#include <QCoreApplication>
#include <QEvent>
#include <QEventLoop>
#include <QThread>
#include <QTimer>
#include <xos/thread_core.hpp>
#include <cstdio>

class BoundaryReceiver final : public QObject {
public:
    QEventLoop *loop = nullptr;
    unsigned received = 0;
    bool event(QEvent *event) override {
        if (event->type() == QEvent::User) {
            ++received;
            loop->quit();
            return true;
        }
        return QObject::event(event);
    }
};

class TimerOwner final : public QObject {
public:
    unsigned *destroyed;
    QTimer timer;
    explicit TimerOwner(unsigned *counter) : destroyed(counter) { timer.setParent(this); }
    ~TimerOwner() override { ++*destroyed; }
};

class TimerWorker final : public QThread {
public:
    unsigned destroyed = 0;
    unsigned ticks = 0;
    bool registered = false;
    bool activeOnExit = false;
    void run() override {
        auto *owner = new TimerOwner(&destroyed);
        // Qt's normal finish path must deliver DeferredDelete before destroying
        // the worker dispatcher, even though this repeating timer stays active.
        QObject::connect(this, &QThread::finished, owner, &QObject::deleteLater);
        QObject::connect(&owner->timer, &QTimer::timeout, owner, [&] {
            if (++ticks == 2) quit();
        });
        owner->timer.setTimerType(Qt::PreciseTimer);
        owner->timer.start(20);
        auto *dispatcher = QAbstractEventDispatcher::instance();
        registered = dispatcher && dispatcher->registeredTimers(&owner->timer).size() == 1;
        exec();
        activeOnExit = owner->timer.isActive();
    }
};

class SpuriousWaker final : public QThread {
public:
    alignas(4) xos::u32 word = 0;
    int woken = 0;
    void run() override {
        for (unsigned i = 0; i < 2; ++i) {
            msleep(20);
            // Deliberately leave the predicate unchanged: a wake alone is not
            // work, and the waiter must reuse its original absolute deadline.
            const auto result = xos::thread::wake(&word);
            if (result < 0) { woken = -100; return; }
            woken += int(result);
        }
    }
};

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    SpuriousWaker spurious;
    spurious.start();
    const auto deadline = xos::thread::clock() + 200000000ULL;
    unsigned wakeReturns = 0;
    for (;;) {
        const auto result = xos::thread::wait(&spurious.word, 0, deadline);
        if (result == xos::thread_error_timeout) break;
        if (result != 0) return 87;
        ++wakeReturns;
    }
    if (xos::thread::clock() < deadline || !spurious.wait(3000) ||
        wakeReturns == 0 || spurious.woken < 1 || spurious.word != 0) return 88;
    auto *dispatcher = QAbstractEventDispatcher::instance();
    for (unsigned i = 0; i < 16; ++i) {
        QEventLoop loop;
        BoundaryReceiver receiver;
        receiver.loop = &loop;
        bool injected = false;
        auto connection = QObject::connect(dispatcher, &QAbstractEventDispatcher::aboutToBlock,
                                           &receiver, [&] {
            if (!injected) {
                injected = true;
                QCoreApplication::postEvent(&receiver, new QEvent(QEvent::User));
            }
        }, Qt::DirectConnection);
        QTimer guard;
        guard.setSingleShot(true);
        QObject::connect(&guard, &QTimer::timeout, &loop, &QEventLoop::quit);
        guard.start(3000);
        loop.exec();
        QObject::disconnect(connection);
        if (!injected || receiver.received != 1 || !guard.isActive()) return 80;
    }
    xos::thread_stats before{}, after{};
    if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&before))) return 81;
    for (unsigned i = 0; i < 8; ++i) {
        TimerWorker worker;
        worker.start();
        if (!worker.wait(3000)) return 82;
        if (worker.ticks != 2 || !worker.registered || !worker.activeOnExit || worker.destroyed != 1)
            return 83;
        if (QAbstractEventDispatcher::instance(&worker)) return 84;
    }
    if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&after))) return 85;
    if (before.threads != after.threads || before.reserved != after.reserved ||
        before.process_kernel_stack_pages != after.process_kernel_stack_pages) return 86;
    std::puts("QT_LIFECYCLE_OK spurious-absolute-deadline check-to-block=16 worker-timer-exit=8 deferred-delete dispatcher-destroyed thread-baseline");
    return 0;
}
