// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtGui/QColor>
#include <QtCore/QByteArray>
namespace aurora {
inline constexpr int token_version = 2;
enum class Scheme { midnight, daybreak };
enum class Quality { high, balanced, low, safe };
struct Preferences {
    Scheme scheme = Scheme::midnight;
    bool high_contrast = false;
    bool reduce_transparency = false;
    bool reduce_motion = false;
    bool glass_enabled = true;
    Quality quality = Quality::balanced;
};
// Semantic values shared by native chrome and the future controlled Web bridge.
struct Tokens {
    QColor background, horizon, light, accent, secondary, warm;
    QColor text, muted, content, control, border, focus, danger;
    int grid = 8, inset = 24, panel_radius = 28, control_radius = 12;
    int font_body = 15, font_caption = 12, font_title = 30;
    int control_height = 36, blur_scale = 8, blur_radius = 2, hover_ms = 120, switch_ms = 180;
    int glass_alpha = 190;
};
Preferences preferences();
Tokens tokens();
// GUI-thread only, process-local. No cross-process settings service is implied.
void set_preferences(const Preferences &value);
QByteArray theme_json();
QByteArray theme_css_variables();
}
