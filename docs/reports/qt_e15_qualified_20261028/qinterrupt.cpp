// SPDX-License-Identifier: Apache-2.0
#include <QAbstractEventDispatcher>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QThread>
#include <xos/thread_core.hpp>
#include <cstdio>
class Interrupter : public QThread {
public:
    QAbstractEventDispatcher *dispatcher = nullptr;
    bool wasWaiting = false;
    void run() override {
        QThread::msleep(50);
        xos::thread_stats stats{};
        if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0)
            wasWaiting = stats.waiting > 0;
        dispatcher->interrupt();
    }
};
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    auto *dispatcher = QAbstractEventDispatcher::instance();
    dispatcher->processEvents(QEventLoop::AllEvents);
    Interrupter worker; worker.dispatcher = dispatcher; worker.start();
    QElapsedTimer elapsed; elapsed.start();
    dispatcher->processEvents(QEventLoop::WaitForMoreEvents);
    auto ms = elapsed.elapsed();
    if (!worker.wait(3000) || !worker.wasWaiting || ms < 30 || ms > 2000) return 70;
    std::puts("QT_INTERRUPT_ONLY_OK no-posted-events blocked wake joined");
    return 0;
}
