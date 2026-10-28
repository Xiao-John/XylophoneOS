// SPDX-License-Identifier: Apache-2.0
#include <QByteArray>
#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QFile>
#include <QMutex>
#include <QThread>
#include <QTimer>
#include <QWaitCondition>
#include <cstdio>

class Worker : public QThread {
public:
    QMutex mutex;
    QWaitCondition ready;
    bool waiting = false;
    bool released = false;
    bool signaled = false;
    void run() override {
        mutex.lock();
        waiting = true;
        while (!released) {
            if (!ready.wait(&mutex, 1000)) break;
        }
        signaled = released;
        mutex.unlock();
    }
};

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (argc > 1 && QByteArray(argv[1]) == "readonly") {
        QFile locked(QStringLiteral("/bin/LOCK.TXT"));
        if (locked.open(QIODevice::WriteOnly) || locked.error() == QFileDevice::NoError) return 23;
        std::puts("QT_READONLY_ERROR_OK");
        return 0;
    }
    if (argc > 1 && QByteArray(argv[1]) == "full") {
        QFile full(QStringLiteral("/bin/FULL.TXT"));
        if (!full.open(QIODevice::WriteOnly | QIODevice::Truncate)) {
            if (full.error() == QFileDevice::NoError) return 24;
        } else {
            QByteArray block(8192, 'x');
            const qint64 written = full.write(block);
            const bool flushed = full.flush();
            if (written == block.size() && flushed) return 25;
            if (full.error() == QFileDevice::NoError) return 26;
        }
        std::puts("QT_FULL_ERROR_OK");
        return 0;
    }
    if (argc > 1 && QByteArray(argv[1]) == "verify") {
        QFile persisted(QStringLiteral("/bin/QTTEST.TXT"));
        if (!persisted.open(QIODevice::ReadOnly) || persisted.readAll() != QByteArray("abc\0z", 5)) return 21;
        std::puts("QT_PERSIST_READ_OK");
        return 0;
    }
    if (QString::fromUtf8("hello").toUpper() != QStringLiteral("HELLO")) return 10;
    QByteArray bytes("ab\0cd", 5);
    if (bytes.size() != 5 || bytes.mid(2, 2) != QByteArray("\0c", 2)) return 11;
    QFile missing(QStringLiteral("/bin/NOTEXIST.TXT"));
    if (missing.open(QIODevice::ReadOnly) || missing.error() == QFileDevice::NoError) return 12;
    QFile file(QStringLiteral("/bin/QTTEST.TXT"));
    if (!file.open(QIODevice::ReadWrite | QIODevice::Truncate)) return 13;
    if (file.write("abc\0z", 5) != 5 || !file.flush() || !file.seek(0)) return 14;
    if (file.read(8) != QByteArray("abc\0z", 5) || !file.atEnd() || !file.read(1).isEmpty()) return 15;
    if (file.map(0, 1) != nullptr || file.error() == QFileDevice::NoError) return 22;
    file.close();
    QDir dir(QStringLiteral("/bin"));
    if (!dir.exists() || !dir.entryList(QDir::Files).contains(QStringLiteral("QTTEST.TXT"))) return 16;
    QFile resource(QStringLiteral(":/probe/message.txt"));
    if (!resource.open(QIODevice::ReadOnly) || resource.readAll() != QByteArray("qt-resource\n")) return 17;

    QEventLoop timerLoop;
    QElapsedTimer elapsed;
    bool fired = false;
    bool canceled = false;
    QTimer cancel;
    cancel.setSingleShot(true);
    QObject::connect(&cancel, &QTimer::timeout, [&] { canceled = true; });
    cancel.start(10);
    cancel.stop();
    elapsed.start();
    QTimer::singleShot(60, &timerLoop, [&] { fired = true; timerLoop.quit(); });
    QTimer::singleShot(3000, &timerLoop, &QEventLoop::quit);
    timerLoop.exec();
    if (!fired || canceled || elapsed.elapsed() < 60) return 18;

    Worker worker;
    QEventLoop threadLoop;
    QObject::connect(&worker, &QThread::finished, &threadLoop, &QEventLoop::quit);
    QTimer::singleShot(100, &threadLoop, [&] {
        worker.mutex.lock();
        worker.released = true;
        worker.ready.wakeOne();
        worker.mutex.unlock();
    });
    QTimer::singleShot(3000, &threadLoop, &QEventLoop::quit);
    worker.start();
    threadLoop.exec();
    if (!worker.wait(3000) || !worker.waiting || !worker.signaled) return 19;
    QMutex mutex;
    QWaitCondition timeout;
    mutex.lock();
    elapsed.restart();
    bool woke = timeout.wait(&mutex, 50);
    mutex.unlock();
    if (woke || elapsed.elapsed() < 50) return 20;
    std::puts("QT_CORE_EXTENDED_OK strings files resource timer cancel qthread mutex condition timeout");
    return 0;
}
