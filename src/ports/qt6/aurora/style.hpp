// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtWidgets/QApplication>
namespace aurora {
// Opt-in Qt Widgets style and palette. Does not affect Qt Quick or other apps.
void initialize(QApplication &app);
}
