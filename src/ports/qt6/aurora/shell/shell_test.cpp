// SPDX-License-Identifier: Apache-2.0
#include "background.h"
#include "docker.h"
#include "windowedge.h"
#include "applicationbrowser.h"
#include <QApplication>
#include <QDir>
#include <QFontDatabase>
#include <QLineEdit>
#include <QMouseEvent>
#include <QPushButton>
#include <QToolButton>
#include <QtTest/QTest>
#include <cstdio>
#include <cstdlib>

static void require(bool condition, const char *message) {
    if (!condition) { std::fprintf(stderr, "FAIL: %s\n", message); std::exit(1); }
}
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    if (argc > 2) require(QFontDatabase::addApplicationFont(QString::fromLocal8Bit(argv[2])) >= 0, "font load");
    app.setStyle(QStringLiteral("Fusion"));
    app.setFont(QFont(QStringLiteral("DejaVu Sans"), 10));
    const QString output = argc > 1 ? QString::fromLocal8Bit(argv[1]) : QStringLiteral(".");
    QDir().mkpath(output);
    Background desktop;
    desktop.show();
    QTest::qWait(100);
    auto *dock = desktop.findChild<Docker *>();
    auto *window = desktop.findChild<WindowEdge *>();
    auto *example = dock->findChild<QToolButton *>("examplewindow");
    auto *muti = dock->findChild<QToolButton *>("muti");
    require(dock && window && example && muti, "shell composition");
    require(desktop.findChild<QWidget *>("Desktop"), "desktop layer");
    require(dock->findChildren<QToolButton *>().size() == 6, "six original Dock icons");
    require(window->width() == qRound(418 * desktop.height() / 768.0), "scaled WindowEdge");
    require(window->state() == WindowEdge::State::Closed, "initially closed");
    require(desktop.grab().save(output + "/desktop.png"), "desktop screenshot");
    QTest::mouseClick(example, Qt::LeftButton);
    QTest::qWait(500);
    require(window->isVisible() && window->state() == WindowEdge::State::Running, "launch");
    require(desktop.grab().save(output + "/window.png"), "window screenshot");
    QTest::mouseClick(example, Qt::LeftButton);
    QTest::qWait(400);
    require(!window->isVisible() && window->state() == WindowEdge::State::Minimized, "minimize");
    require(dock->applicationState("examplewindow") == Docker::ApplicationState::Minimized, "Dock marker");
    QTest::mouseClick(example, Qt::LeftButton);
    QTest::qWait(500);
    require(window->isVisible(), "restore");
    window->minimizeAnimated();
    QTest::qWait(50);
    window->openAnimated(dock->applicationIconGeometry("examplewindow"));
    QTest::qWait(500);
    require(window->isVisible() && window->state() == WindowEdge::State::Running, "reverse minimize");
    const auto drag = [window](QPoint local, QPoint delta) {
        const QPoint global = window->mapToGlobal(local);
        QMouseEvent press(QEvent::MouseButtonPress, local, global, Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(window, &press);
        QMouseEvent move(QEvent::MouseMove, local + delta, global + delta, Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
        QApplication::sendEvent(window, &move);
        QMouseEvent release(QEvent::MouseButtonRelease, window->mapFromGlobal(global + delta), global + delta,
                            Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
        QApplication::sendEvent(window, &release);
    };
    const QRect initial = window->geometry();
    drag(QPoint(window->width()/2, 1), QPoint(12, 10));
    require(window->size() == initial.size(), "top edge never resizes");
    require(window->pos() == initial.topLeft() + QPoint(12, 10), "title drag");
    const int oldWidth = window->width();
    drag(QPoint(window->width()-1, window->height()/2), QPoint(20, 0));
    require(window->width() == oldWidth+20, "right resize");
    drag(QPoint(0, window->height()/2), QPoint(-10, 0));
    require(window->width() == oldWidth+30, "left resize");
    const int oldHeight = window->height();
    drag(QPoint(window->width()/2, window->height()-1), QPoint(0, 15));
    require(window->height() == oldHeight+15, "bottom resize");
    auto *max = window->findChild<QPushButton *>("MaximizeButton");
    QTest::mouseClick(max, Qt::LeftButton);
    QTest::qWait(800);
    require(window->isMaximized() && window->width() == desktop.width(), "maximize");
    require(dock->y() >= desktop.height(), "maximized Dock autohide");
    QTest::mouseClick(max, Qt::LeftButton);
    QTest::qWait(500);
    require(!window->isMaximized() && dock->y() < desktop.height(), "unmaximize reveals Dock");
    QTest::mouseClick(muti, Qt::LeftButton);
    QTest::qWait(600);
    auto *browser = desktop.findChild<ApplicationBrowser *>();
    auto *search = browser->findChild<QLineEdit *>("ApplicationSearch");
    require(browser->isVisible() && !search->hasFocus(), "menu opens without search focus");
    browser->dismiss();
    QTest::qWait(50);
    browser->open();
    QTest::qWait(600);
    require(browser->isVisible(), "reverse browser close");
    require(browser->findChildren<QToolButton *>(QRegularExpression("^app_")).size() == 4, "catalog groups");
    require(desktop.grab().save(output + "/browser.png"), "browser screenshot");
    QTest::mouseClick(search, Qt::LeftButton);
    QTest::keyClicks(search, "EXAMPLE");
    require(browser->findChildren<QToolButton *>(QRegularExpression("^app_")).size() == 1, "case-insensitive search");
    auto *tile = browser->findChild<QToolButton *>("app_examplewindow");
    QTest::mouseClick(tile, Qt::LeftButton);
    require(browser->isVisible(), "launch waits for closing animation");
    QTest::qWait(500);
    require(!browser->isVisible() && window->isVisible(), "menu launch completed");
    QTest::mouseClick(window->findChild<QPushButton *>("CloseButton"), Qt::LeftButton);
    require(window->state() == WindowEdge::State::Closed, "close state");
    require(dock->applicationState("examplewindow") == Docker::ApplicationState::Closed, "closed marker");
    std::puts("PASS: composition, scale, launch/minimize/restore/close, maximize/autohide, catalog/search/deferred launch");
}
