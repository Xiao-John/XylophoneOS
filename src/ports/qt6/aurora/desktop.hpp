// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "aurora.hpp"
#include "theme.hpp"
#include "blur.hpp"
#include <new>
namespace aurora {
struct RenderInfo {
    Quality effective=Quality::balanced;
    qint64 cache_bytes=0, cache_ns=0;
    unsigned generations=0;
    bool fallback=false;
};
// Application-local background only. No cross-process pixels or device rights.
class desktop_surface : public QWidget {
    QImage background,softened;
    aurora::pointer *pointer;
    int wallpaper=0,cached_wallpaper=-1,cached_key=-1;
    qint64 budget=8*1024*1024;
    RenderInfo info;
    int key() const {
        const auto p=preferences();return int(p.scheme)+int(p.quality)*2+
            (p.high_contrast?16:0)+(p.reduce_transparency?32:0)+(p.glass_enabled?64:0);
    }
    void wallpaper_paint(QPainter &p) {
        const auto t=tokens();p.setRenderHint(QPainter::Antialiasing);
        QLinearGradient base(0,0,width(),height());base.setColorAt(0,t.background);
        base.setColorAt(.55,t.horizon);base.setColorAt(1,t.background);p.fillRect(rect(),base);
        for(int i=0;i<3;++i){
            const auto center=QPointF(width()*(i==0?.1:i==1?.85:.6),height()*(i==2?.95:.1));
            QColor c=i==0?t.light:i==1?t.secondary:t.warm;c.setAlpha(i==2?65:95);
            QRadialGradient g(center,width()*(wallpaper?.65:.85));g.setColorAt(0,c);c.setAlpha(0);g.setColorAt(1,c);p.fillRect(rect(),g);
        }
        for(int i=0;i<5;++i){
            QPainterPath ribbon;ribbon.moveTo(-40,height()*(.7+i*.055));
            ribbon.cubicTo(width()*.35,height()*(wallpaper?.15:.94),width()*.55,-height()*.12,width()+50,height()*(.15+i*.055));
            QColor c=i%2?t.secondary:t.accent;c.setAlpha(18+i*5);
            p.setPen(QPen(c,24-i*3,Qt::SolidLine,Qt::RoundCap));p.drawPath(ribbon);
        }
    }
    void cache() {
        if(size().isEmpty())return;
        QElapsedTimer timer;timer.start();const auto t=tokens();
        cached_key=key();cached_wallpaper=wallpaper;
        background={};softened={};info.effective=preferences().quality;info.fallback=false;
        const qint64 full=qint64(width())*height()*4;
        try {
            if(full<=budget){background=QImage(size(),QImage::Format_RGB32);
                if(!background.isNull()){QPainter p(&background);wallpaper_paint(p);}}
            if(background.isNull()){info.effective=Quality::safe;info.fallback=true;}
            if(t.glass_alpha<255 && !background.isNull()) {
                int level=int(info.effective);
                for(;level<3;++level){
                    const auto quality_start=timer.nsecsElapsed();
                    const int scale=level==0?2:level==1?8:16,radius=level==0?6:level==1?2:1;
                    const int w=qMax(1,width()/scale),h=qMax(1,height()/scale);
                    if(full*2+qint64(w)*h*12>budget)continue;
                    auto small=background.scaled(w,h,Qt::IgnoreAspectRatio,Qt::SmoothTransformation).convertToFormat(QImage::Format_ARGB32_Premultiplied);
                    QImage scratch(small.size(),small.format()),blurred(small.size(),small.format());
                    if(small.isNull() || scratch.isNull() || blurred.isNull())continue;
                    if(!box_blur_argb32(reinterpret_cast<const std::uint32_t*>(small.constBits()),reinterpret_cast<std::uint32_t*>(blurred.bits()),reinterpret_cast<std::uint32_t*>(scratch.bits()),w,h,std::size_t(w)*h,radius))continue;
                    softened=blurred.scaled(size(),Qt::IgnoreAspectRatio,Qt::SmoothTransformation);
                    if(softened.isNull())continue;
                    // Cache generation budget; report and try the lower quality.
                    if(level<2 && timer.nsecsElapsed()-quality_start>250000000){softened={};continue;}
                    break;
                }
                info.effective=Quality(qMin(level,3));
                info.fallback=info.effective!=preferences().quality;
            }
        } catch(const std::bad_alloc &) {softened={};info.effective=Quality::safe;info.fallback=true;}
        info.cache_bytes=background.sizeInBytes()+softened.sizeInBytes();info.cache_ns=timer.nsecsElapsed();++info.generations;
        std::printf("AURORA_DESKTOP_CACHE bytes=%lld ns=%lld wallpaper=%d requested=%d effective=%d fallback=%d budget=%lld generations=%u\n",(long long)info.cache_bytes,(long long)info.cache_ns,wallpaper,int(preferences().quality),int(info.effective),info.fallback,(long long)budget,info.generations);
    }
protected:
    void resizeEvent(QResizeEvent *e) override {QWidget::resizeEvent(e);cache();}
    void paintEvent(QPaintEvent *) override {
        if(cached_key!=key() || cached_wallpaper!=wallpaper)cache();
        QPainter p(this);
        if(background.isNull())p.fillRect(rect(),tokens().background);
        else p.drawImage(0,0,background);
    }
    bool eventFilter(QObject *object,QEvent *event) override {
        if(event->type()==QEvent::MouseMove){auto *w=qobject_cast<QWidget*>(object);
            if(w && w->window()==this){auto *m=static_cast<QMouseEvent*>(event);pointer->move(mapFromGlobal(m->globalPosition().toPoint()));pointer->show();pointer->raise();}}
        return QWidget::eventFilter(object,event);
    }
public:
    desktop_surface():pointer(new aurora::pointer(this)){qApp->installEventFilter(this);setMouseTracking(true);}
    void set_cache_budget(qint64 bytes){budget=qMax<qint64>(0,bytes);cache();update();for(auto *w:findChildren<QWidget*>())w->update();}
    void set_wallpaper(int value){wallpaper=value?1:0;cache();update();for(auto *w:findChildren<QWidget*>())w->update();}
    RenderInfo render_info() const {return info;}
    bool sample(QPainter &p,const QWidget *widget) {
        if(cached_key!=key() || cached_wallpaper!=wallpaper)cache();
        if(softened.isNull())return false;
        p.drawImage(widget->rect(),softened,QRect(widget->mapTo(this,QPoint()),widget->size()));return true;
    }
};
class glass_panel : public QWidget {
    desktop_surface *surface;
    bool content;
protected:
    void paintEvent(QPaintEvent *) override {
        const auto t=tokens();QPainter p(this);p.setRenderHint(QPainter::Antialiasing);
        const auto r=QRectF(rect()).adjusted(1,1,-1,-1);const auto path=corner(r,t.panel_radius);
        p.save();p.setClipPath(path);
        const bool sampled=!content && t.glass_alpha<255 && surface->sample(p,this);
        auto fill=t.content;fill.setAlpha(sampled?t.glass_alpha:255);p.fillRect(rect(),fill);
        if(sampled){QLinearGradient sheen(0,0,0,65);sheen.setColorAt(0,QColor(255,255,255,25));sheen.setColorAt(1,Qt::transparent);p.fillRect(rect(),sheen);}
        p.restore();p.setPen(QPen(t.border,preferences().high_contrast?2:1));p.drawPath(path);
        if(sampled){p.setPen(QColor(255,255,255,45));p.drawPath(corner(r.adjusted(2,2,-2,-2),t.panel_radius-2));}
    }
public:
    explicit glass_panel(desktop_surface *parent,bool reading=false):QWidget(parent),surface(parent),content(reading){}
};
}
