// SPDX-License-Identifier: Apache-2.0
// Qt QMutex slow-path timeout followed by a real wake, in an XOS guest.
#include <QByteArray>
#include <QCoreApplication>
#include <QElapsedTimer>
#include <QMutex>
#include <QThread>
#include <atomic>
#include <cstdio>
class Holder : public QThread {
public:
    QMutex mutex;
    std::atomic<bool> locked{false};
    void run() override {
        mutex.lock(); locked.store(true);
        QThread::msleep(200);
        mutex.unlock();
    }
};
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    Holder holder;
    holder.start();
    QElapsedTimer startup; startup.start();
    while (!holder.locked.load() && startup.elapsed() < 1000) QThread::msleep(10);
    if (!holder.locked.load()) return 60;
    QElapsedTimer elapsed; elapsed.start();
    if (holder.mutex.tryLock(50)) { holder.mutex.unlock(); return 61; }
    if (elapsed.elapsed() < 50) return 62;
    if (!holder.mutex.tryLock(2000)) return 63;
    holder.mutex.unlock();
    if (!holder.wait(3000)) return 64;
    std::puts("QT_MUTEX_CONTENTION_OK timeout no-early-expiry wake join");
    return 0;
}
