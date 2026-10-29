// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtWidgets/QApplication>
#include "theme.hpp"
namespace aurora {
// Opt-in Qt Widgets style and palette. Does not affect Qt Quick or other apps.
void initialize(QApplication &app);
void select_style(QApplication &app, bool glass);
}
