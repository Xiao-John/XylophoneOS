// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QGuiApplication>
#include <QScreen>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>

// The display dimensions come from Interactium's negotiated QPA screen.
// This catalog describes the design's launchers, not installed executable files.
// Only examplewindow currently has an implementation; other launchers are reserved.
inline QJsonObject auroraSystemConfiguration()
{
    const QSize size = QGuiApplication::primaryScreen()->geometry().size();
    return {{"background", QJsonObject{{"width", size.width()}, {"height", size.height()},
                                      {"image", ":/aurora/wallpaper.bmp"}}},
            {"docker", QJsonObject{
                {"frontapps", QJsonArray{"file", "setting", "browser", "examplewindow", "trash"}},
                {"allapps", QJsonArray{"examplewindow", "file", "setting", "browser"}},
                {"icon", QJsonObject{{"file", "icon/file.svg"}, {"setting", "icon/setting.svg"},
                                     {"trash", "icon/trash.svg"},
                                     {"examplewindow", "icon/unknown/unknown_E.svg"}}}}}};
}

inline QString auroraIconPath(const QString &name, const QString &configured)
{
    QString path = QStringLiteral(":/aurora/") + configured;
    if (configured.isEmpty() || !QFile::exists(path))
        path = QStringLiteral(":/aurora/icon/unknown/unknown_%1.svg").arg(name.left(1).toUpper());
    return path;
}
