// SPDX-License-Identifier: Apache-2.0
#include "theme.hpp"
#include "style.hpp"
#include <QtWidgets/QApplication>
#include <QtWidgets/QWidget>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtGui/QPalette>
#include <cstdio>
namespace aurora {
namespace { Preferences current; }
Preferences preferences() { return current; }
Tokens tokens() {
    Tokens t;
    if (current.scheme == Scheme::midnight) {
        t.background = QColor("#08172e"); t.horizon = QColor("#292152");
        t.light = QColor("#137a89"); t.accent = QColor("#81dfea");
        t.secondary = QColor("#ada4f5"); t.warm = QColor("#f5bb9d");
        t.text = QColor("#edf5ff"); t.muted = QColor("#b6cce4");
        t.content = QColor("#12223b"); t.control = QColor("#294264");
        t.border = QColor("#6587a9"); t.focus = QColor("#a1e8ff");
        t.danger = QColor("#ffb6b9");
    } else {
        t.background = QColor("#d7e6ef"); t.horizon = QColor("#cfc9eb");
        t.light = QColor("#8acdd4"); t.accent = QColor("#135c72");
        t.secondary = QColor("#6056a6"); t.warm = QColor("#e5af86");
        t.text = QColor("#142d46"); t.muted = QColor("#395574");
        t.content = QColor("#f4f8fc"); t.control = QColor("#d9e6ef");
        t.border = QColor("#738ca5"); t.focus = QColor("#125c9d");
        t.danger = QColor("#9a2442"); t.panel_radius = 20; t.glass_alpha = 218;
    }
    if (current.high_contrast) {
        const bool dark = current.scheme == Scheme::midnight;
        t.text = dark ? Qt::white : Qt::black; t.muted = t.text;
        t.content = dark ? QColor("#081424") : QColor("#ffffff");
        t.border = t.text; t.glass_alpha = 255;
    }
    if (current.reduce_transparency) t.glass_alpha = 255;
    switch(current.quality) {
    case Quality::high:t.blur_scale=2;t.blur_radius=6;break;
    case Quality::balanced:t.blur_scale=8;t.blur_radius=2;break;
    case Quality::low:t.blur_scale=16;t.blur_radius=1;break;
    case Quality::safe:t.glass_alpha=255;t.blur_radius=0;break;
    }
    if(!current.glass_enabled)t.glass_alpha=255;
    if (current.reduce_motion) t.hover_ms = t.switch_ms = 0;
    return t;
}
void set_preferences(const Preferences &value) {
    current = value; if (!qApp) return;
    select_style(*qApp,current.glass_enabled && current.quality!=Quality::safe);
    const auto t = tokens(); QPalette p;
    p.setColor(QPalette::Window,t.content); p.setColor(QPalette::WindowText,t.text);
    p.setColor(QPalette::Base,t.content); p.setColor(QPalette::AlternateBase,t.control);
    p.setColor(QPalette::Text,t.text); p.setColor(QPalette::Button,t.control);
    p.setColor(QPalette::ButtonText,t.text); p.setColor(QPalette::Highlight,t.accent);
    p.setColor(QPalette::HighlightedText,t.content); p.setColor(QPalette::ToolTipBase,t.content);
    p.setColor(QPalette::ToolTipText,t.text); p.setColor(QPalette::Disabled,QPalette::Text,t.muted);
    p.setColor(QPalette::Disabled,QPalette::ButtonText,t.muted);
    qApp->setPalette(p);
    for (const char *name : {"QWidget","QLabel","QPlainTextEdit","QLineEdit","QPushButton"})
        qApp->setPalette(p,name);
    QFont f(QStringLiteral("DejaVu Sans")); f.setPixelSize(t.font_body); qApp->setFont(f);
    // QApplication propagates its palette to widgets that inherit it. Do not
    // overwrite a third-party widget's explicitly chosen palette.
    for (auto *w : QApplication::allWidgets()) w->update();
    std::printf("AURORA_THEME v=2 scheme=%d contrast=%d opaque=%d motion=%d\n",
        int(current.scheme),current.high_contrast,current.reduce_transparency,current.reduce_motion);
}
QByteArray theme_json() {
    const auto t = tokens();
    return QJsonDocument(QJsonObject{
        {"version",token_version},{"scope","process-local"},
        {"scheme",current.scheme == Scheme::midnight ? "midnight" : "daybreak"},
        {"text",t.text.name()},{"muted",t.muted.name()},{"content",t.content.name()},
        {"control",t.control.name()},{"accent",t.accent.name()},{"focus",t.focus.name()},
        {"danger",t.danger.name()},{"border",t.border.name()},
        {"grid",t.grid},{"inset",t.inset},{"panelRadius",t.panel_radius},
        {"controlRadius",t.control_radius},{"fontFamily","DejaVu Sans"},
        {"fontBody",t.font_body},{"fontCaption",t.font_caption},{"fontTitle",t.font_title},
        {"controlHeight",t.control_height},{"blurScale",t.blur_scale},{"blurRadius",t.blur_radius},
        {"quality",int(current.quality)},{"glassEnabled",current.glass_enabled},
        {"glassAlpha",t.glass_alpha},{"hoverMs",t.hover_ms},{"switchMs",t.switch_ms},
        {"highContrast",current.high_contrast},{"reduceTransparency",current.reduce_transparency},
        {"reduceMotion",current.reduce_motion}}).toJson(QJsonDocument::Compact);
}
QByteArray theme_css_variables() {
    const auto t=tokens();QByteArray css;
    auto color=[&](const char *name,QColor value){css+="--xos-aurora-";css+=name;css+=":";css+=value.name().toUtf8();css+=";";};
    auto number=[&](const char *name,int value,const char *unit){css+="--xos-aurora-";css+=name;css+=":";css+=QByteArray::number(value);css+=unit;css+=";";};
    color("text",t.text);color("muted",t.muted);color("content",t.content);color("control",t.control);
    color("accent",t.accent);color("focus",t.focus);color("danger",t.danger);color("border",t.border);
    number("grid",t.grid,"px");number("inset",t.inset,"px");number("panel-radius",t.panel_radius,"px");
    number("control-radius",t.control_radius,"px");number("font-body",t.font_body,"px");
    number("hover-duration",t.hover_ms,"ms");number("switch-duration",t.switch_ms,"ms");
    css+="--xos-aurora-font-family:'DejaVu Sans',sans-serif;";return css;
}
}
