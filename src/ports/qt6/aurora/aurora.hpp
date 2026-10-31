// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtWidgets/QWidget>
#include <QtWidgets/QPushButton>
#include <QtWidgets/QApplication>
#include <QtGui/QMouseEvent>
#include <QtGui/QPainter>
#include <QtGui/QPainterPath>
#include <QtGui/QPaintEvent>
#include <QtGui/QResizeEvent>
#include <QtCore/QTimer>
#include <QtCore/QElapsedTimer>
#include <cstdio>
namespace aurora {
// Eight cubic segments. Zero initial curvature at straight edges, shared
// tangent at each diagonal join; this is our own squircle approximation.
inline QPainterPath corner(QRectF r,qreal radius) {
    const qreal a=qMin(radius,qMin(r.width(),r.height())/2),k=.1591*a;
    const auto x=r.left(),y=r.top(),w=r.width(),h=r.height();
    QPainterPath p;p.moveTo(x+a,y);p.lineTo(x+w-a,y);
    p.cubicTo(x+w-.55*a,y,x+w-.3182*a,y,x+w-k,y+k);
    p.cubicTo(x+w,y+.3182*a,x+w,y+.55*a,x+w,y+a);
    p.lineTo(x+w,y+h-a);
    p.cubicTo(x+w,y+h-.55*a,x+w,y+h-.3182*a,x+w-k,y+h-k);
    p.cubicTo(x+w-.3182*a,y+h,x+w-.55*a,y+h,x+w-a,y+h);
    p.lineTo(x+a,y+h);
    p.cubicTo(x+.55*a,y+h,x+.3182*a,y+h,x+k,y+h-k);
    p.cubicTo(x,y+h-.3182*a,x,y+h-.55*a,x,y+h-a);
    p.lineTo(x,y+a);
    p.cubicTo(x,y+.55*a,x,y+.3182*a,x+k,y+k);
    p.cubicTo(x+.3182*a,y,x+.55*a,y,x+a,y);p.closeSubpath();return p;
}
class pointer final : public QWidget {
 void paintEvent(QPaintEvent *) override {QPainter p(this);p.setRenderHint(QPainter::Antialiasing);QPainterPath a;a.moveTo(2,2);a.lineTo(2,20);a.lineTo(7,15);a.lineTo(11,23);a.lineTo(14,21);a.lineTo(10,14);a.lineTo(17,14);a.closeSubpath();p.translate(1,1);p.fillPath(a,QColor(0,5,18,110));p.translate(-1,-1);p.setPen(QPen(QColor(16,28,46),1));p.setBrush(QColor(237,245,255));p.drawPath(a);}
public:explicit pointer(QWidget *p):QWidget(p){setFixedSize(20,26);setAttribute(Qt::WA_TransparentForMouseEvents);setAttribute(Qt::WA_NoSystemBackground);hide();}
};
class canvas : public QWidget {
    QImage backdrop,soft;
    aurora::pointer *pointer;
    void cache() {
        QElapsedTimer timer;timer.start();
        backdrop=QImage(size(),QImage::Format_RGB32);backdrop.fill(QColor(9,18,38));
        QPainter p(&backdrop);p.setRenderHint(QPainter::Antialiasing);
        QLinearGradient base(0,0,width(),height());base.setColorAt(0,QColor(13,44,64));base.setColorAt(.5,QColor(17,25,52));base.setColorAt(1,QColor(43,28,64));p.fillRect(rect(),base);
        const QImage wallpaper(QStringLiteral(":/xos/aurora.bmp"));
        if(!wallpaper.isNull()) {p.drawImage(rect(),wallpaper);p.fillRect(rect(),QColor(5,11,29,48));}
        else {
            for(auto c:{QColor(67,194,203,130),QColor(125,92,215,105),QColor(229,170,154,45)}) {
                const int i=c.red();QPointF center(i<100?width()*.08:width()*.95,i>200?height()*.9:height()*.12);
                QRadialGradient glow(center,width()*.7);glow.setColorAt(0,c);c.setAlpha(0);glow.setColorAt(1,c);p.fillRect(rect(),glow);
            }
            QPainterPath ribbon;ribbon.moveTo(-80,height()*.65);ribbon.cubicTo(width()*.25,height()*.9,width()*.48,-100,width()+80,40);
            for(int w=100;w>0;w-=5){p.setPen(QPen(QColor(93,210,223,2),w,Qt::SolidLine,Qt::RoundCap));p.drawPath(ribbon);}
        }
        p.end();
        // Cache a low-frequency optical background once per resize, never per key.
        soft=backdrop.scaled(qMax(1,width()/16),qMax(1,height()/16),Qt::IgnoreAspectRatio,Qt::SmoothTransformation)
                     .scaled(size(),Qt::IgnoreAspectRatio,Qt::SmoothTransformation);
        std::printf("AURORA_CACHE bytes=%lld ns=%lld\n",(long long)(backdrop.sizeInBytes()+soft.sizeInBytes()),(long long)timer.nsecsElapsed());
    }
protected:
    bool eventFilter(QObject *object,QEvent *event) override {
        if(event->type()==QEvent::MouseMove) {
            auto *widget=qobject_cast<QWidget*>(object);
            if(widget && widget->window()==this){auto *mouse=static_cast<QMouseEvent*>(event);pointer->move(mapFromGlobal(mouse->globalPosition().toPoint()));pointer->raise();pointer->show();}
        }
        return QWidget::eventFilter(object,event);
    }
    void resizeEvent(QResizeEvent *e) override {QWidget::resizeEvent(e);if(!size().isEmpty())cache();}
    void paintEvent(QPaintEvent *) override {
        QPainter p(this);p.setRenderHint(QPainter::Antialiasing);p.drawImage(0,0,backdrop);
        const auto panel=corner(QRectF(rect()).adjusted(18,18,-18,-18),32);
        for(int i=10;i>0;--i){p.setPen(QPen(QColor(1,5,17,3),i*2));p.drawPath(panel);}
        p.fillPath(panel,QColor(30,46,79,98));
        p.save();p.setClipPath(panel);QLinearGradient shade(0,0,202,0);shade.setColorAt(0,QColor(7,17,38,95));shade.setColorAt(1,QColor(18,34,62,40));p.fillRect(QRect(18,18,184,height()-36),shade);p.restore();
        QLinearGradient edge(20,20,width()-20,height()-20);edge.setColorAt(0,QColor(195,244,255,180));edge.setColorAt(.45,QColor(155,160,231,40));edge.setColorAt(1,QColor(116,225,223,170));
        p.setPen(QPen(edge,1));p.drawPath(panel);
        p.setPen(QColor(159,192,220,35));p.drawLine(202,38,202,height()-38);
    }
public:
    canvas():pointer(new aurora::pointer(this)){qApp->installEventFilter(this);setMouseTracking(true);}
    QImage glass(const QWidget *w) const {
        return soft.copy(QRect(w->mapTo(this,QPoint()),w->size()));
    }
};
class panel : public QWidget {
    aurora::canvas *canvas;
    QImage cached;
    qreal radius;
    bool reading;
protected:
    void resizeEvent(QResizeEvent *e) override {QWidget::resizeEvent(e);cached={};}
    void paintEvent(QPaintEvent *) override {
        QPainter p(this);p.setRenderHint(QPainter::Antialiasing);
        const QRectF r=QRectF(rect()).adjusted(.5,.5,-.5,-.5);const auto path=corner(r,radius);
        p.save();p.setClipPath(path);
        if(!reading){if(cached.size()!=size())cached=canvas->glass(this);p.drawImage(0,0,cached);}
        QLinearGradient fill(0,0,width(),height());
        fill.setColorAt(0,reading?QColor(19,27,47,249):QColor(127,159,203,58));
        fill.setColorAt(1,reading?QColor(16,23,42,251):QColor(47,63,107,100));p.fillRect(rect(),fill);
        QLinearGradient sheen(0,0,0,44);sheen.setColorAt(0,QColor(230,247,255,reading?8:25));sheen.setColorAt(1,Qt::transparent);p.fillRect(rect(),sheen);p.restore();
        QLinearGradient edge(0,0,width(),height());edge.setColorAt(0,QColor(217,242,255,100));edge.setColorAt(.45,QColor(176,194,237,30));edge.setColorAt(1,QColor(122,215,214,85));p.setPen(QPen(edge,1));p.drawPath(path);
    }
public:
    panel(aurora::canvas *c,qreal r,bool content=false):QWidget(c),canvas(c),radius(r),reading(content){setAttribute(Qt::WA_StyledBackground,false);}
};
class button final : public QPushButton {
    QTimer transition;
    qreal glow=0,target=0;
    bool primary;
    bool reduced=false;
    void aim(qreal v){target=v;if(reduced){glow=v;update();}else transition.start();}
protected:
    void enterEvent(QEnterEvent *e) override {QPushButton::enterEvent(e);aim(1);}
    void leaveEvent(QEvent *e) override {QPushButton::leaveEvent(e);aim(0);}
    void paintEvent(QPaintEvent *) override {
        QElapsedTimer timer;timer.start();QPainter p(this);p.setRenderHint(QPainter::Antialiasing);
        auto r=QRectF(rect()).adjusted(1,1,-1,-1);if(isDown())r.adjust(1,1,-1,-1);
        auto path=corner(r,qMin<qreal>(14,height()/2));
        if(!isEnabled())p.setOpacity(.45);
        QLinearGradient fill(0,0,0,height());
        if(primary){fill.setColorAt(0,QColor(116,177,255));fill.setColorAt(.52,QColor(86,112,229));fill.setColorAt(1,QColor(117,95,194));}
        else{fill.setColorAt(0,QColor(179,206,245,25+int(glow*30)));fill.setColorAt(1,QColor(84,105,164,40+int(glow*35)));}
        p.fillPath(path,fill);p.setPen(QColor(205,225,255,primary?170:45+int(glow*60)));p.drawPath(path);
        if(isDown())p.fillPath(path,QColor(4,11,33,55));
        if(hasFocus()){p.setPen(QPen(QColor(151,214,255,200),1));p.drawPath(corner(r.adjusted(2,2,-2,-2),12));}
        p.setPen(QColor(239,244,255));p.drawText(rect(),Qt::AlignCenter,text());p.end();
        const auto ns=timer.nsecsElapsed();if(ns>35000000 && !reduced){reduced=true;transition.stop();glow=target;std::printf("AURORA_REDUCED_MOTION paint_ns=%lld\n",(long long)ns);}
    }
public:
    button(QString label,bool accent=false):QPushButton(label),primary(accent) {
        setMinimumHeight(34);setCursor(Qt::PointingHandCursor);transition.setInterval(33);
        connect(&transition,&QTimer::timeout,this,[this]{const auto d=target-glow;if(qAbs(d)<.05){glow=target;transition.stop();}else glow+=d*.45;update();});
    }
};
class brand final : public QWidget {
protected:
 void paintEvent(QPaintEvent *) override {QPainter p(this);p.setRenderHint(QPainter::Antialiasing);const QColor c[]={QColor(104,222,212),QColor(122,185,255),QColor(184,151,246),QColor(226,188,210)};const int h[]={14,24,34,20};for(int i=0;i<4;i++){p.setPen(QPen(c[i],4,Qt::SolidLine,Qt::RoundCap));p.drawLine(8+i*8,24-h[i]/2,8+i*8,24+h[i]/2);}p.setPen(QColor(237,242,252));QFont f=font();f.setPixelSize(15);f.setBold(true);p.setFont(f);p.drawText(46,21,"Xylophone");f.setPixelSize(12);f.setBold(false);p.setFont(f);p.setPen(QColor(180,198,222));p.drawText(46,39,"Notes");}
public:brand(){setFixedHeight(52);}
};
}
