// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "content.hpp"
#include <litehtml.h>
#include <QtWidgets/QAbstractScrollArea>
#include <QtWidgets/QScrollBar>
#include <QtGui/QPainter>
#include <QtGui/QFontMetrics>
#include <QtGui/QMouseEvent>
#include <QtGui/QKeyEvent>
#include <QtCore/QTimer>
#include <QtCore/QMap>
#include <functional>
#include <cstdio>
#include <stdexcept>
namespace browser {
class HtmlView final:public QAbstractScrollArea,public litehtml::document_container {
    litehtml::document::ptr doc;
    QPainter *painter=nullptr;
    QMap<QString,QImage> images;
    QString page,caption;
    int imports=0,fonts=0,clipDepth=0;
    bool layoutBusy=false;
    static QColor color(litehtml::web_color c){return QColor(c.red,c.green,c.blue,c.alpha);}
    static QRect box(const litehtml::position &r){return QRect(r.x,r.y,r.width,r.height);}
    QString resource(const char *src,const char *base){return resolve(QString::fromUtf8(src),base&&*base?QString::fromUtf8(base):page);}
    // Report the first anchor in global coordinates after every layout. The view can
    // still be unsized while load() runs, so a point printed only there would stay
    // stale after the resize that follows and would miss where the link is drawn.
    void log_anchor(){if(!doc)return;auto anchor=doc->root()->select_one("a");if(!anchor)return;
        auto r=anchor->get_placement();auto p=viewport()->mapToGlobal(QPoint(r.x+qMax(8,r.width/2),r.y+qMax(10,r.height/2)));
        std::printf("BROWSER_ANCHOR point=%d,%d\n",p.x(),p.y());}
    void relayout(){if(!doc||layoutBusy)return;
        struct Reset { bool &flag; ~Reset(){flag=false;} } reset{layoutBusy};layoutBusy=true;
        try{doc->render(viewport()->width());verticalScrollBar()->setRange(0,qMin(65536,qMax(0,doc->height()-viewport()->height())));verticalScrollBar()->setPageStep(viewport()->height());}
        catch(const std::exception&){doc.reset();std::printf("BROWSER_LAYOUT_FAILED resource-budget\n");}viewport()->update();log_anchor();}
    void eventAt(QMouseEvent *event,int kind){if(!doc)return;litehtml::position::vector dirty;int x=int(event->position().x()),y=int(event->position().y());if(kind==0)doc->on_mouse_over(x,y+verticalScrollBar()->value(),x,y,dirty);if(kind==1)doc->on_lbutton_down(x,y+verticalScrollBar()->value(),x,y,dirty);if(kind==2)doc->on_lbutton_up(x,y+verticalScrollBar()->value(),x,y,dirty);if(!dirty.empty())viewport()->update();}
protected:
    void paintEvent(QPaintEvent*)override {QPainter p(viewport());p.fillRect(viewport()->rect(),Qt::white);if(!doc)return;painter=&p;clipDepth=0;litehtml::position clip(0,0,viewport()->width(),viewport()->height());doc->draw(0,0,-verticalScrollBar()->value(),&clip);while(clipDepth>0){p.restore();--clipDepth;}painter=nullptr;}
    void resizeEvent(QResizeEvent *event)override{QAbstractScrollArea::resizeEvent(event);relayout();}
    void mouseMoveEvent(QMouseEvent *event)override{eventAt(event,0);}
    void mousePressEvent(QMouseEvent *event)override{if(event->button()==Qt::LeftButton)eventAt(event,1);}
    void mouseReleaseEvent(QMouseEvent *event)override{if(event->button()==Qt::LeftButton)eventAt(event,2);}
    void leaveEvent(QEvent*)override{if(doc){litehtml::position::vector dirty;doc->on_mouse_leave(dirty);viewport()->update();}}
    void keyPressEvent(QKeyEvent *e)override{int d=0;if(e->key()==Qt::Key_Down)d=40;else if(e->key()==Qt::Key_Up)d=-40;else if(e->key()==Qt::Key_PageDown)d=viewport()->height()-40;else if(e->key()==Qt::Key_PageUp)d=40-viewport()->height();else if(e->key()==Qt::Key_Home){verticalScrollBar()->setValue(0);return;}else if(e->key()==Qt::Key_End){verticalScrollBar()->setValue(verticalScrollBar()->maximum());return;}else{QAbstractScrollArea::keyPressEvent(e);return;}verticalScrollBar()->setValue(verticalScrollBar()->value()+d);}
public:
    std::function<void(QString)> navigate;
    std::function<void(QString)> titleChanged;
    HtmlView(QWidget *parent):QAbstractScrollArea(parent){setFrameShape(QFrame::NoFrame);viewport()->setMouseTracking(true);setFocusPolicy(Qt::StrongFocus);setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);connect(verticalScrollBar(),&QScrollBar::valueChanged,this,[this](int value){viewport()->update();std::printf("BROWSER_SCROLL value=%d max=%d\n",value,verticalScrollBar()->maximum());});}
    bool load(const QString &path,QString &error){QByteArray bytes;if(!read(path,bytes,32768,error)||!html_allowed(bytes,error))return false;
        doc.reset();images.clear();page=path;caption.clear();imports=0;fonts=0;verticalScrollBar()->setValue(0);
        try{doc=litehtml::document::createFromString(bytes.constData(),this);relayout();if(!doc){error="Layout resource budget failed";return false;}if(doc->height()>65536){doc.reset();error="Layout height budget exceeded";return false;}}
        catch(const std::exception &reason){layoutBusy=false;doc.reset();
            // liteHTML lets the stylesheet callback exceptions escape; report them as
            // stylesheet admission failures instead of an engine allocation error.
            const std::string cause=reason.what();
            if(cause=="stylesheet rejected")error="Stylesheet rejected";
            else if(cause=="CSS quota")error="Stylesheet import quota exceeded";
            else error="Engine allocation or resource budget failed";
            return false;}
        if(!doc){error="Engine did not create document";return false;}
        if(titleChanged)titleChanged(caption.isEmpty()?path.section('/',-1):caption);
        std::printf("BROWSER_LOADED path=%s bytes=%d width=%d height=%d fonts=%d images=%lld imports=%d\n",page.toUtf8().constData(),int(bytes.size()),doc->width(),doc->height(),fonts,(long long)images.size(),imports);log_anchor();viewport()->update();return true;}
    QString current()const{return page;}
    litehtml::uint_ptr create_font(const char*,int size,int weight,litehtml::font_style italic,unsigned int decoration,litehtml::font_metrics *fm)override {if(++fonts>128)throw std::runtime_error("font quota");auto *f=new QFont("DejaVu Sans");f->setPixelSize(qBound(6,size,96));f->setWeight(QFont::Weight(qBound(100,weight,900)));f->setItalic(italic==litehtml::font_style_italic);f->setUnderline(decoration&litehtml::font_decoration_underline);f->setStrikeOut(decoration&litehtml::font_decoration_linethrough);QFontMetrics m(*f);if(fm){fm->height=m.height();fm->ascent=m.ascent();fm->descent=m.descent();fm->x_height=m.xHeight();fm->draw_spaces=true;}return reinterpret_cast<litehtml::uint_ptr>(f);}
    void delete_font(litehtml::uint_ptr f)override{delete reinterpret_cast<QFont*>(f);--fonts;}
    int text_width(const char *s,litehtml::uint_ptr f)override {return QFontMetrics(*reinterpret_cast<QFont*>(f)).horizontalAdvance(QString::fromUtf8(s));}
    void draw_text(litehtml::uint_ptr,const char *s,litehtml::uint_ptr f,litehtml::web_color c,const litehtml::position &r)override {if(!painter)return;auto &font=*reinterpret_cast<QFont*>(f);painter->setFont(font);painter->setPen(color(c));painter->drawText(r.x,r.y+QFontMetrics(font).ascent(),QString::fromUtf8(s));}
    int pt_to_px(int p)const override{return p*96/72;}
    int get_default_font_size()const override{return 16;}
    const char *get_default_font_name()const override{return "DejaVu Sans";}
    void draw_list_marker(litehtml::uint_ptr,const litehtml::list_marker &m)override {if(!painter)return;painter->setPen(color(m.color));painter->setBrush(color(m.color));if(m.marker_type==litehtml::list_style_type_decimal)painter->drawText(box(m.pos),QString::number(m.index)+".");else painter->drawEllipse(box(m.pos));}
    void load_image(const char *src,const char *base,bool)override {auto path=resource(src,base);if(path.isEmpty()||images.contains(path))return;if(images.size()>=8)throw std::runtime_error("image quota");QByteArray data;QString error;if(!path.endsWith(".bmp")||!read(path,data,1048630,error)||data.size()<54||data.mid(0,2)!="BM"){std::printf("BROWSER_RESOURCE_REJECT image\n");return;}
        auto u32=[&](int offset){return quint32(quint8(data[offset]))|(quint32(quint8(data[offset+1]))<<8)|(quint32(quint8(data[offset+2]))<<16)|(quint32(quint8(data[offset+3]))<<24);};
        // Only uncompressed Windows BMP, bounded positive dimensions before Qt.
        auto w=u32(18),h=u32(22);if(u32(14)!=40||w==0||h==0||w>512||h>512||u32(30)!=0||quint8(data[28])!=24||quint8(data[29])!=0){std::printf("BROWSER_RESOURCE_REJECT bmp-header\n");return;}
        auto image=QImage::fromData(data,"BMP");if(!image.isNull())images.insert(path,image);}
    void get_image_size(const char *src,const char *base,litehtml::size &s)override{load_image(src,base,false);auto im=images.value(resource(src,base));s.width=im.width();s.height=im.height();}
    void draw_background(litehtml::uint_ptr,const std::vector<litehtml::background_paint>& bg)override {if(!painter)return;for(auto i=bg.rbegin();i!=bg.rend();++i){painter->save();painter->setClipRect(box(i->clip_box),Qt::IntersectClip);painter->fillRect(box(i->border_box),color(i->color));auto image=images.value(resource(i->image.c_str(),i->baseurl.c_str()));if(!image.isNull())painter->drawImage(QRect(i->position_x,i->position_y,qBound(0,i->image_size.width,4096),qBound(0,i->image_size.height,4096)),image);painter->restore();}}
    void draw_borders(litehtml::uint_ptr,const litehtml::borders &b,const litehtml::position &r,bool)override {if(!painter)return;auto edge=[&](const litehtml::border &v,QRect where){if(v.width>0&&v.style==litehtml::border_style_solid)painter->fillRect(where,color(v.color));};edge(b.top,QRect(r.x,r.y,r.width,qBound(0,b.top.width,32)));edge(b.bottom,QRect(r.x,r.bottom()-qBound(0,b.bottom.width,32),r.width,qBound(0,b.bottom.width,32)));edge(b.left,QRect(r.x,r.y,qBound(0,b.left.width,32),r.height));edge(b.right,QRect(r.right()-qBound(0,b.right.width,32),r.y,qBound(0,b.right.width,32),r.height));}
    void set_caption(const char *s)override{caption=QString::fromUtf8(s).left(128);std::printf("BROWSER_TITLE %s\n",caption.toUtf8().constData());}
    void set_base_url(const char*)override{} // HTML <base> is outside admitted tags.
    void link(const litehtml::document::ptr&,const litehtml::element::ptr&)override{}
    void on_anchor_click(const char *url,const litehtml::element::ptr&)override{auto target=resolve(QString::fromUtf8(url),page);std::printf("BROWSER_LINK target=%s\n",target.toUtf8().constData());if(navigate)QTimer::singleShot(0,this,[this,target]{navigate(target);});}
    void set_cursor(const char *s)override{viewport()->setCursor(QByteArray(s)=="pointer"?Qt::PointingHandCursor:Qt::ArrowCursor);}
    void transform_text(litehtml::string &s,litehtml::text_transform type)override{auto q=QString::fromUtf8(s.c_str());if(type==litehtml::text_transform_uppercase)q=q.toUpper();else if(type==litehtml::text_transform_lowercase)q=q.toLower();s=q.toUtf8().constData();}
    void import_css(litehtml::string &text,const litehtml::string &url,litehtml::string &base)override {text.clear();if(++imports>8)throw std::runtime_error("CSS quota");auto path=resource(url.c_str(),base.c_str());QByteArray bytes;QString error;if(path.isEmpty()||!path.endsWith(".css")||!read(path,bytes,8192,error)||!css_allowed(bytes)){std::printf("BROWSER_RESOURCE_REJECT css\n");throw std::runtime_error("stylesheet rejected");}std::printf("BROWSER_CSS_LOADED path=%s bytes=%d\n",path.toUtf8().constData(),int(bytes.size()));text.assign(bytes.constData(),bytes.size());base=path.toUtf8().constData();}
    void set_clip(const litehtml::position &p,const litehtml::border_radiuses&)override{if(painter){painter->save();++clipDepth;painter->setClipRect(box(p),Qt::IntersectClip);}}
    void del_clip()override{if(painter&&clipDepth>0){painter->restore();--clipDepth;}}
    void get_client_rect(litehtml::position &r)const override{r=litehtml::position(0,0,viewport()->width(),viewport()->height());}
    litehtml::element::ptr create_element(const char*,const litehtml::string_map&,const litehtml::document::ptr&)override{return {};}
    void get_media_features(litehtml::media_features &m)const override{m.type=litehtml::media_type_screen;m.width=m.device_width=viewport()->width();m.height=m.device_height=viewport()->height();m.color=8;m.resolution=96;}
    void get_language(litehtml::string &l,litehtml::string &c)const override{l="en";c="en-US";}
};
}
