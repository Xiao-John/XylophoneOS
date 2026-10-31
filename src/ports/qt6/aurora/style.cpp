// SPDX-License-Identifier: Apache-2.0
#include "style.hpp"
#include "aurora.hpp"
#include "theme.hpp"
#include <QtWidgets/QProxyStyle>
#include <QtWidgets/QStyleFactory>
#include <QtWidgets/QStyleOptionButton>
#include <QtWidgets/QStyleOptionFrame>
#include <QtWidgets/QLineEdit>
#include <QtGui/QPalette>
#include <QtCore/QVariant>
static void init_aurora_resource() { Q_INIT_RESOURCE(xos_aurora); }
namespace aurora {
namespace {
class style final : public QProxyStyle {
public:
    style():QProxyStyle(QStyleFactory::create("Fusion")) {setObjectName("Xylophone Aurora Glass");}
    void polish(QWidget *w) override {QProxyStyle::polish(w);w->setAttribute(Qt::WA_Hover);w->setMouseTracking(true);}
    void drawControl(ControlElement element,const QStyleOption *option,QPainter *p,const QWidget *w=nullptr) const override {
        if(element!=CE_PushButton){QProxyStyle::drawControl(element,option,p,w);return;}
        const auto *b=qstyleoption_cast<const QStyleOptionButton*>(option);
        if(!b){QProxyStyle::drawControl(element,option,p,w);return;}
        p->save();p->setRenderHint(QPainter::Antialiasing);
        const bool enabled=b->state&State_Enabled,hover=b->state&State_MouseOver,down=b->state&State_Sunken;
        const bool accent=(b->features&QStyleOptionButton::DefaultButton) || (w && w->property("auroraAccent").toBool());
        const auto t=tokens();
        auto r=QRectF(b->rect).adjusted(1,1,-1,-1);if(down)r.adjust(1,1,-1,-1);
        const auto path=corner(r,t.control_radius);QLinearGradient fill(r.topLeft(),r.bottomLeft());
        fill.setColorAt(0,accent?t.accent:t.control.lighter(hover?125:110));
        fill.setColorAt(1,accent?t.accent.darker(110):t.control);
        if(!enabled)p->setOpacity(.45);
        p->fillPath(path,fill);if(down)p->fillPath(path,QColor(4,12,29,70));
        p->setPen(t.border);p->drawPath(path);
        if(b->state&State_HasFocus){p->setPen(QPen(t.focus,2));p->drawPath(corner(r.adjusted(3,3,-3,-3),t.control_radius-3));}
        // Let Qt render the standard label, including icons and mnemonics,
        // while keeping the Aurora panel and its intended foreground color.
        auto label=*b;if(!(w&&w->testAttribute(Qt::WA_SetPalette)))label.palette.setColor(QPalette::ButtonText,accent?t.content:t.text);
        QProxyStyle::drawControl(CE_PushButtonLabel,&label,p,w);p->restore();
    }
    void drawPrimitive(PrimitiveElement element,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        if(element==PE_PanelLineEdit) {
            const auto t=tokens();
            p->save();p->setRenderHint(QPainter::Antialiasing);const auto path=corner(QRectF(o->rect).adjusted(1,1,-1,-1),t.control_radius);
            p->fillPath(path,o->palette.color(QPalette::Base));p->setPen(QPen((o->state&State_HasFocus)?t.focus:t.border,(o->state&State_HasFocus)?2:1));p->drawPath(path);p->restore();return;
        }
        if(element==PE_IndicatorCheckBox) {
            const auto t=tokens();p->save();p->setRenderHint(QPainter::Antialiasing);
            const auto r=QRectF(o->rect).adjusted(1,1,-1,-1);
            p->fillPath(corner(r,5),(o->state&State_On)?t.accent:t.content);
            p->setPen(QPen((o->state&State_HasFocus)?t.focus:t.border,2));p->drawPath(corner(r,5));
            if(o->state&State_On){p->setPen(QPen(t.content,2));p->drawLine(r.topLeft()+QPointF(3,7),r.topLeft()+QPointF(6,10));p->drawLine(r.topLeft()+QPointF(6,10),r.topLeft()+QPointF(12,3));}
            p->restore();return;
        }
        QProxyStyle::drawPrimitive(element,o,p,w);
    }
};
}
void initialize(QApplication &app) {
    init_aurora_resource();
    set_preferences(preferences());
}
void select_style(QApplication &app,bool glass) {
    const auto name=glass?QStringLiteral("Xylophone Aurora Glass"):QStringLiteral("fusion");
    if(app.style()->objectName().compare(name,Qt::CaseInsensitive)!=0)
        app.setStyle(glass?static_cast<QStyle*>(new style):QStyleFactory::create("Fusion"));
}
}
