// SPDX-License-Identifier: Apache-2.0
#include <QEventLoop>
#include <QGuiApplication>
#include <QQmlError>
#include <QQmlEngine>
#include <QQuickItem>
#include <QQuickView>
#include <QSGRendererInterface>
#include <QTimer>
#include <QtPlugin>
#include <xos/thread_core.hpp>

#include <cstdio>

Q_IMPORT_PLUGIN(QXosIntegrationPlugin)

namespace {
bool run_scene(int cycle)
{
    QQuickView view;
    view.setPosition(32, 40);
    view.engine()->setImportPathList({QStringLiteral("qrc:/qt/qml"),
                                    QStringLiteral("qrc:/qt-project.org/imports")});
    view.setSource(QUrl(QStringLiteral("qrc:/quick/scene.qml")));
    if (view.status() != QQuickView::Ready || !view.rootObject()) {
        for (const auto &error : view.errors())
            std::fprintf(stderr, "%s\n", qPrintable(error.toString()));
        return false;
    }

    QEventLoop loop;
    QTimer monitor;
    int frames = 0;
    xos::u32 sampled_peak_pages = 0;
    xos::u64 previous_frame = 0;
    xos::u64 max_frame_interval = 0;
    bool passed = false;
    bool key_reported = false;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &loop, [&] {
        const auto now = xos::thread::clock();
        if (previous_frame != 0)
            max_frame_interval = qMax(max_frame_interval, now - previous_frame);
        previous_frame = now;
        xos::thread_stats stats{};
        if (xos::sdk::syscall(xos::sys_thread_stats, reinterpret_cast<xos::u64>(&stats)) == 0)
            sampled_peak_pages = qMax(sampled_peak_pages, stats.process_user_pages);
        if (++frames == 1) {
            if (view.rendererInterface()->graphicsApi() != QSGRendererInterface::Software) {
                loop.quit();
                return;
            }
            std::printf("QT_QUICK_FRAME cycle=%d\n", cycle);
            std::fflush(stdout);
        }
    });
    QObject::connect(&monitor, &QTimer::timeout, &loop, [&] {
        const auto *root = view.rootObject();
        if (frames >= 2 && root->property("ticks").toInt() >= 2
            && root->property("key_hits").toInt() >= 1) {
            if (!key_reported) {
                key_reported = true;
                std::printf("QT_QUICK_KEY cycle=%d\n", cycle);
                std::fflush(stdout);
            }
            if (root->property("acknowledged").toBool() && sampled_peak_pages != 0) {
                passed = true;
                std::printf("QT_QUICK_SCENE_OK cycle=%d frames=%d sampled_peak_pages=%u "
                            "max_frame_interval_ns=%llu\n", cycle, frames, sampled_peak_pages,
                            static_cast<unsigned long long>(max_frame_interval));
                std::fflush(stdout);
                loop.quit();
            }
        }
    });

    QTimer::singleShot(30000, &loop, &QEventLoop::quit);
    monitor.start(25);
    view.show();
    view.requestActivate();
    loop.exec();
    view.close();
    return passed;
}
}

int main(int argc, char **argv)
{
    qputenv("QT_QPA_PLATFORM", "xos");
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Software);
    QGuiApplication app(argc, argv);
    app.setQuitOnLastWindowClosed(false);
    for (int cycle = 1; cycle <= 2; ++cycle) {
        if (!run_scene(cycle)) {
            std::fprintf(stderr, "QT_QUICK_FAIL cycle=%d\n", cycle);
            return 1;
        }
    }
    std::puts("QT_QUICK_SMOKE_OK");
    return 0;
}
