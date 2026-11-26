// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QSGRendererInterface>
#include <QTimer>
#include <QtPlugin>

#include <cstdio>

Q_IMPORT_PLUGIN(QXosIntegrationPlugin)

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", "xos");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    QQmlApplicationEngine engine;
    engine.loadFromModule("Xos.QuickExample", "Main");

    const auto roots = engine.rootObjects();
    if (roots.size() != 1)
        return 1;
    auto *window = qobject_cast<QQuickWindow *>(roots.front());
    if (!window)
        return 1;

    bool software_frame = false;
    QObject::connect(window, &QQuickWindow::frameSwapped, &app, [&] {
        if (!software_frame && window->rendererInterface()->graphicsApi() == QSGRendererInterface::Software) {
            software_frame = true;
            std::puts("QT_QUICK_EXTERNAL_FRAME");
            std::fflush(stdout);
        }
    });
    QTimer::singleShot(10000, &app, [&] { app.exit(2); });
    const int status = app.exec();
    return software_frame ? status : 1;
}
