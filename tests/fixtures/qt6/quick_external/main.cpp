// SPDX-License-Identifier: Apache-2.0
#include <QEventLoop>
#include <QGuiApplication>
#include <QQmlEngine>
#include <QQmlError>
#include <QQuickItem>
#include <QQuickView>
#include <QSGRendererInterface>
#include <QTimer>
#include <QtPlugin>

#include <cstdio>

Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
Q_IMPORT_PLUGIN(QtQuick2Plugin)
Q_IMPORT_PLUGIN(QtQmlPlugin)
Q_IMPORT_PLUGIN(QtQmlModelsPlugin)
Q_IMPORT_PLUGIN(QtQuick_WindowPlugin)

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", "xos");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    QQuickView view;
    view.setPosition(32, 40);
    view.engine()->setImportPathList({QStringLiteral("qrc:/qt/qml"),
                                    QStringLiteral("qrc:/qt-project.org/imports")});
    view.setSource(QUrl::fromLocalFile(QStringLiteral("/usr/share/quick-file/Scene.qml")));
    if (view.status() != QQuickView::Ready || !view.rootObject()) {
        for (const auto &error : view.errors())
            std::fprintf(stderr, "%s\n", qPrintable(error.toString()));
        return 1;
    }

    const auto *root = view.rootObject();
    const auto tag = root->property("palette_tag").toString().toUtf8();
    QEventLoop loop;
    QTimer monitor;
    bool rendered = false;
    bool reached_active = false;
    bool passed = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &loop, [&] {
        if (rendered)
            return;
        if (view.rendererInterface()->graphicsApi() != QSGRendererInterface::Software) {
            loop.quit();
            return;
        }
        rendered = true;
        std::printf("QT_QUICK_FILE_FRAME tag=%s\n", tag.constData());
        std::fflush(stdout);
    });
    QObject::connect(&monitor, &QTimer::timeout, &loop, [&] {
        if (!rendered || root->property("state").toString() != QStringLiteral("active"))
            return;
        if (!reached_active) {
            reached_active = true;
            std::printf("QT_QUICK_FILE_STATE tag=%s state=active\n", tag.constData());
            std::fflush(stdout);
        }
        if (root->property("confirmed").toBool()) {
            passed = true;
            loop.quit();
        }
    });
    QTimer::singleShot(45000, &loop, &QEventLoop::quit);
    monitor.start(25);
    view.show();
    view.requestActivate();
    loop.exec();
    view.close();
    if (!passed)
        return 1;
    std::puts("QT_QUICK_FILE_OK");
    return 0;
}
