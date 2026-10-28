// SPDX-License-Identifier: Apache-2.0
// Target-side G03 fixture; a successful build is not a guest qualification.
#include <QByteArray>
#include <QCoreApplication>
#include <QFile>
#include <QObject>
#include <QThread>
#include <QTimer>
#include <cstdio>

class Sender final : public QObject {
    Q_OBJECT
public:
    void send() { emit sent(QStringLiteral("cross-thread")); }
signals:
    void sent(const QString &text);
};

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (QString::fromUtf8("XOS") != QStringLiteral("XOS") || QByteArray("abc").size() != 3)
        return 1;
    QFile resource(QStringLiteral(":/probe/message.txt"));
    if (!resource.open(QIODevice::ReadOnly) || resource.readAll() != QByteArray("qt-resource\n"))
        return 2;
    QThread thread;
    Sender sender;
    sender.moveToThread(&thread);
    bool received = false;
    QObject::connect(&thread, &QThread::started, &sender, &Sender::send);
    QObject::connect(&sender, &Sender::sent, &app, [&](const QString &s) {
        received = s == QStringLiteral("cross-thread");
        app.quit();
    }, Qt::QueuedConnection);
    QTimer::singleShot(3000, &app, &QCoreApplication::quit);
    thread.start();
    app.exec();
    thread.quit();
    if (!thread.wait(3000) || !received)
        return 3;
    std::puts("QT_CORE_SMOKE_OK");
    return 0;
}
#include "core_smoke.moc"
