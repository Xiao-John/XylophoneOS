// SPDX-License-Identifier: Apache-2.0
#include <QCoreApplication>
#include <QByteArray>
#include <QAbstractEventDispatcher>
#include <QElapsedTimer>
#include <QEvent>
#include <QEventLoop>
#include <QThread>
#include <QSocketNotifier>
#include <QTimer>
#include <xos/thread_core.hpp>
#include <cstdio>

class Receiver : public QObject {
public:
    QEventLoop *loop = nullptr;
    int count = 0;
    bool event(QEvent *event) override {
        if (event->type() == QEvent::User) {
            if (++count == 32) loop->quit();
            return true;
        }
        return QObject::event(event);
    }
};
class Poster : public QThread {
public:
    Receiver *receiver;
    QAbstractEventDispatcher *dispatcher;
    bool observedWait = false;
    void run() override {
        QThread::msleep(50);
        xos::thread_stats stats{};
        if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0)
            observedWait = stats.waiting > 0;
        std::printf("QT_EVENT_RESOURCE_SAMPLE user_pages=%u kernel_stack_pages=%u waiting=%u\n",
                    stats.process_user_pages, stats.process_kernel_stack_pages, stats.waiting);
        for (int i = 0; i < 32; ++i)
            QCoreApplication::postEvent(receiver, new QEvent(QEvent::User));
        dispatcher->interrupt();
    }
};
class SleepingWorker : public QThread {
    void run() override { QThread::msleep(1000); }
};
class FaultWorker : public QThread {
    void run() override { QThread::msleep(5000); }
};
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (argc > 1 && QByteArray(argv[1]) == "quota") {
        SleepingWorker workers[4];
        for (auto &worker : workers) worker.start();
        if (workers[3].isRunning()) return 32;
        for (int i = 0; i < 3; ++i) if (!workers[i].wait(3000)) return 33;
        std::puts("QT_THREAD_QUOTA_OK fourth-rejected first-three-joined");
        return 0;
    }
    if (argc > 1 && QByteArray(argv[1]) == "fault") {
        FaultWorker worker;
        worker.start();
        QThread::msleep(50);
        std::puts("QT_FAULT_TRIGGER");
        __builtin_trap();
    }
    QSocketNotifier unsupported(1, QSocketNotifier::Read);
    if (unsupported.isEnabled()) return 34;
    unsupported.setEnabled(true);
    if (unsupported.isEnabled()) return 35;
    QEventLoop outer;
    bool nested = false;
    bool timerEarly = false;
    QTimer::singleShot(30, &outer, [&] {
        QEventLoop inner;
        QElapsedTimer elapsed; elapsed.start();
        QTimer::singleShot(30, &inner, &QEventLoop::quit);
        inner.exec();
        timerEarly = elapsed.elapsed() < 30;
        nested = true;
        outer.quit();
    });
    QTimer::singleShot(3000, &outer, &QEventLoop::quit);
    outer.exec();
    if (!nested || timerEarly) return 30;
    QEventLoop posted;
    Receiver receiver;
    receiver.loop = &posted;
    Poster poster;
    poster.receiver = &receiver;
    poster.dispatcher = QAbstractEventDispatcher::instance();
    QTimer::singleShot(3000, &posted, &QEventLoop::quit);
    poster.start();
    posted.exec();
    if (!poster.wait(3000) || receiver.count != 32 || !poster.observedWait) return 31;
    std::puts("QT_EVENTS_OK unsupported-notifier nested timer posted interrupt blocked-state joined");
    return 0;
}
