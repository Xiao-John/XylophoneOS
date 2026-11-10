// SPDX-License-Identifier: Apache-2.0
// Aurora shell: design components hosted by the Interactium Qt platform.
#include "shell/background.h"
#include <QApplication>
#include <QFont>
#include <QtPlugin>
#include <cstdio>
#ifdef __XOS__
Q_IMPORT_PLUGIN(QXosIntegrationPlugin)
#endif
int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName(QStringLiteral("Aurora"));
    app.setStyle(QStringLiteral("Fusion"));
    app.setFont(QFont(QStringLiteral("DejaVu Sans"), 10));
    Background desktop;
    desktop.show();
    std::printf("[aurora] ready: design desktop %dx%d\n", desktop.width(), desktop.height());
    return app.exec();
}
