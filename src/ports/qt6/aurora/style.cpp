// SPDX-License-Identifier: Apache-2.0
#include "style.hpp"
#include "aurora.hpp"
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
class Style final : public QProxyStyle {
public:
    Style():QProxyStyle(QStyleFactory::create("Fusion")) {setObjectName("Xylophone Aurora Glass");}
    void polish(QWidget *w) override {QProxyStyle::polish(w);w->setPalette(qApp->palette());w->setAttribute(Qt::WA_Hover);w->setMouseTracking(true);}
    void drawControl(ControlElement element,const QStyleOption *option,QPainter *p,const QWidget *w=nullptr) const override {
        if(element!=CE_PushButton){QProxyStyle::drawControl(element,option,p,w);return;}
        const auto *b=qstyleoption_cast<const QStyleOptionButton*>(option);
        if(!b){QProxyStyle::drawControl(element,option,p,w);return;}
        p->save();p->setRenderHint(QPainter::Antialiasing);
        const bool enabled=b->state&State_Enabled,hover=b->state&State_MouseOver,down=b->state&State_Sunken;
        const bool accent=(b->features&QStyleOptionButton::DefaultButton) || (w && w->property("auroraAccent").toBool());
        auto r=QRectF(b->rect).adjusted(1,1,-1,-1);if(down)r.adjust(1,1,-1,-1);
        const auto path=corner(r,14);QLinearGradient fill(r.topLeft(),r.bottomLeft());
        fill.setColorAt(0,accent?QColor(110,174,250):QColor(83,112,155,hover?190:120));
        fill.setColorAt(1,accent?QColor(106,91,187):QColor(40,56,92,190));
        if(!enabled)p->setOpacity(.45);
        p->fillPath(path,fill);if(down)p->fillPath(path,QColor(4,12,29,70));
        p->setPen(QColor(199,225,248,hover?160:75));p->drawPath(path);
        if(b->state&State_HasFocus){p->setPen(QColor(151,214,255));p->drawPath(corner(r.adjusted(2,2,-2,-2),12));}
        p->setPen(QColor(232,240,252));p->drawText(b->rect,Qt::AlignCenter,b->text);p->restore();
    }
    void drawPrimitive(PrimitiveElement element,const QStyleOption *o,QPainter *p,const QWidget *w=nullptr) const override {
        if(element==PE_PanelLineEdit) {
            p->save();p->setRenderHint(QPainter::Antialiasing);const auto path=corner(QRectF(o->rect).adjusted(.5,.5,-.5,-.5),10);
            p->fillPath(path,QColor(10,22,41,220));p->setPen((o->state&State_HasFocus)?QColor(125,192,224):QColor(87,112,150));p->drawPath(path);p->restore();return;
        }
        QProxyStyle::drawPrimitive(element,o,p,w);
    }
};
}
void initialize(QApplication &app) {
    init_aurora_resource();
    app.setStyle(new Style);
    QPalette p;p.setColor(QPalette::Window,QColor(18,29,51));p.setColor(QPalette::WindowText,QColor(221,231,246));
    p.setColor(QPalette::Base,QColor(18,26,45));p.setColor(QPalette::AlternateBase,QColor(27,39,62));p.setColor(QPalette::Text,QColor(221,231,246));
    p.setColor(QPalette::Button,QColor(50,71,111));p.setColor(QPalette::ButtonText,QColor(232,240,252));
    p.setColor(QPalette::Highlight,QColor(78,100,166));p.setColor(QPalette::HighlightedText,Qt::white);
    p.setColor(QPalette::Disabled,QPalette::Text,QColor(116,131,156));p.setColor(QPalette::Disabled,QPalette::ButtonText,QColor(116,131,156));app.setPalette(p);
    for(const char *name:{"QWidget","QLabel","QPlainTextEdit","QLineEdit","QPushButton"})app.setPalette(p,name);
    QFont f(QStringLiteral("DejaVu Sans"));f.setPixelSize(16);app.setFont(f);
}
}
