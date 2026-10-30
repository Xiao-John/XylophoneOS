// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "content.hpp"
#include "scene_geometry.hpp"
#include "../qt6/aurora/ssg.hpp"
#include <litehtml.h>
#include <QtWidgets/QAbstractScrollArea>
#include <QtWidgets/QScrollBar>
#include <QtGui/QPainter>
#include <QtGui/QFontMetrics>
#include <QtGui/QMouseEvent>
#include <QtGui/QKeyEvent>
#include <QtCore/QTimer>
#include <QtCore/QMap>
#include <QtCore/QJsonDocument>
#include <functional>
#include <memory>
#include <utility>
#include <cstdio>
#include <stdexcept>
#ifdef XOS_SSG_TEST_ORACLE
#include "test_structure_oracle.hpp"
#endif
namespace browser {
class HtmlView final:public QAbstractScrollArea,public litehtml::document_container {
    litehtml::document::ptr doc;
    QPainter *painter=nullptr;
    QMap<QString,QImage> images;
    QString page,caption;
    int imports=0,fonts=0,clipDepth=0;
    bool layoutBusy=false;
    aurora::SceneStream scene;
    bool scene_allowed=false;
    QMap<quintptr,quint64> scene_ids;
    quint64 next_scene_id=1;
    struct PageFrame { litehtml::element::ptr element; quint64 parent; int depth; decltype(std::declval<litehtml::element &>().children().begin()) child; bool entered=false; quint64 id=0; };
    struct PageSession { QVector<PageFrame> stack; QString query,epoch,token,session_id; bool visible=false; unsigned limit=0; quint64 revision=0,sequence=0; QElapsedTimer age; };
    std::unique_ptr<PageSession> page_session;
    QTimer page_expiry;
    quint64 page_revision=1, page_nonce=0;
#ifdef XOS_SSG_TEST_ORACLE
    QByteArray oracle_input_sha256;
#endif
    void invalidate_pages(){++page_revision;page_expiry.stop();page_session.reset();}
    static QColor color(litehtml::web_color c){return QColor(c.red,c.green,c.blue,c.alpha);}
    static QRect box(const litehtml::position &r){return QRect(r.x,r.y,r.width,r.height);}
    QString resource(const char *src,const char *base){return resolve(QString::fromUtf8(src),base&&*base?QString::fromUtf8(base):page);}
    void relayout(){if(!doc||layoutBusy)return;invalidate_pages();
        struct Reset { bool &flag; ~Reset(){flag=false;} } reset{layoutBusy};layoutBusy=true;
        try{doc->render(viewport()->width());verticalScrollBar()->setRange(0,qMin(65536,qMax(0,doc->height()-viewport()->height())));verticalScrollBar()->setPageStep(viewport()->height());}
        catch(const std::exception&){doc.reset();std::printf("BROWSER_LAYOUT_FAILED resource-budget\n");}viewport()->update();}
    void eventAt(QMouseEvent *event,int kind){if(!doc)return;invalidate_pages();litehtml::position::vector dirty;int x=int(event->position().x()),y=int(event->position().y());if(kind==0)doc->on_mouse_over(x,y+verticalScrollBar()->value(),x,y,dirty);if(kind==1)doc->on_lbutton_down(x,y+verticalScrollBar()->value(),x,y,dirty);if(kind==2)doc->on_lbutton_up(x,y+verticalScrollBar()->value(),x,y,dirty);if(!dirty.empty())viewport()->update();}
protected:
    void paintEvent(QPaintEvent*)override {QPainter p(viewport());p.fillRect(viewport()->rect(),Qt::white);if(!doc)return;painter=&p;clipDepth=0;litehtml::position clip(0,0,viewport()->width(),viewport()->height());doc->draw(0,0,-verticalScrollBar()->value(),&clip);while(clipDepth>0){p.restore();--clipDepth;}painter=nullptr;}
    void resizeEvent(QResizeEvent *event)override{QAbstractScrollArea::resizeEvent(event);relayout();}
    void mouseMoveEvent(QMouseEvent *event)override{eventAt(event,0);}
    void mousePressEvent(QMouseEvent *event)override{if(event->button()==Qt::LeftButton)eventAt(event,1);}
    void mouseReleaseEvent(QMouseEvent *event)override{if(event->button()==Qt::LeftButton)eventAt(event,2);}
    void leaveEvent(QEvent*)override{if(doc){invalidate_pages();litehtml::position::vector dirty;doc->on_mouse_leave(dirty);viewport()->update();}}
    void keyPressEvent(QKeyEvent *e)override{int d=0;if(e->key()==Qt::Key_Down)d=40;else if(e->key()==Qt::Key_Up)d=-40;else if(e->key()==Qt::Key_PageDown)d=viewport()->height()-40;else if(e->key()==Qt::Key_PageUp)d=40-viewport()->height();else if(e->key()==Qt::Key_Home){verticalScrollBar()->setValue(0);return;}else if(e->key()==Qt::Key_End){verticalScrollBar()->setValue(verticalScrollBar()->maximum());return;}else{QAbstractScrollArea::keyPressEvent(e);return;}verticalScrollBar()->setValue(verticalScrollBar()->value()+d);}
public:
    std::function<void(QString)> navigate;
    std::function<void(QString)> titleChanged;
    HtmlView(QWidget *parent):QAbstractScrollArea(parent){page_expiry.setSingleShot(true);connect(&page_expiry,&QTimer::timeout,this,[this]{page_session.reset();});setFrameShape(QFrame::NoFrame);viewport()->setMouseTracking(true);setFocusPolicy(Qt::StrongFocus);setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);connect(verticalScrollBar(),&QScrollBar::valueChanged,this,[this](int value){invalidate_pages();viewport()->update();std::printf("BROWSER_SCROLL value=%d max=%d\n",value,verticalScrollBar()->maximum());});}
    bool load(const QString &path,QString &error){QByteArray bytes;if(!read(path,bytes,32768,error)||!html_allowed(bytes,error))return false;
#ifdef XOS_SSG_TEST_ORACLE
        oracle_input_sha256=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex();
#endif
        invalidate_pages();doc.reset();scene.invalidate();scene_ids.clear();next_scene_id=1;images.clear();page=path;caption.clear();imports=0;fonts=0;verticalScrollBar()->setValue(0);
        try{doc=litehtml::document::createFromString(bytes.constData(),this);relayout();if(!doc){error="Layout resource budget failed";return false;}if(doc->height()>65536){doc.reset();error="Layout height budget exceeded";return false;}}
        catch(const std::exception&){layoutBusy=false;doc.reset();error="Engine allocation or resource budget failed";return false;}
        if(!doc){error="Engine did not create document";return false;}
        if(titleChanged)titleChanged(caption.isEmpty()?path.section('/',-1):caption);
        std::printf("BROWSER_LOADED path=%s bytes=%d candidate_width=%d candidate_height=%d fonts=%d images=%lld imports=%d\n",page.toUtf8().constData(),int(bytes.size()),doc->width(),doc->height(),fonts,(long long)images.size(),imports);viewport()->update();return true;}
    void log_anchor_point(){
        if(!doc)return;auto anchor=doc->root()->select_one("a");if(!anchor)return;
        litehtml::position::vector fragments;anchor->get_rendering_fragments(fragments,8);
        for(const auto &r:fragments){const QRect clip=QRect(r.x,r.y-verticalScrollBar()->value(),r.width,r.height).intersected(viewport()->rect());
            if(clip.isEmpty())continue;const auto p=viewport()->mapToGlobal(clip.topLeft()+QPoint(qMin(8,clip.width()/2),qMin(10,clip.height()/2)));
            std::printf("BROWSER_ANCHOR point=%d,%d source=final-render-fragment\n",p.x(),p.y());return;}
        std::printf("BROWSER_ANCHOR_UNAVAILABLE outside-viewport-or-not-rendered\n");
    }
    QString current()const{return page;}
#ifdef XOS_SSG_TEST_ORACLE
    QJsonObject test_structure_reference() const {
        // No authority is granted by the test build. The existing explicit
        // document/text permission is still required before any model is read.
        if(!scene_allowed)return {{"status","DENIED"}};
        if(!doc)return {{"status","SEMANTICS_UNAVAILABLE"}};
        auto result=test::structure_oracle(doc->root());
        result["document"]=page;
        result["inputSha256"]=QString::fromLatin1(oracle_input_sha256);
        result["sourceEpoch"]=scene.source_epoch();
        result["sourceRevision"]=QString::number(page_revision);
        const auto window_origin=window()->mapToGlobal(QPoint());
        const auto viewport_origin=viewport()->mapTo(window(),QPoint());
        result["windowOrigin"]=QJsonArray{window_origin.x(),window_origin.y()};
        result["viewportInWindow"]=QJsonArray{viewport_origin.x(),viewport_origin.y(),
                                              viewport()->width(),viewport()->height()};
        return result;
    }
#endif
    void allow_scene_observation(bool value){invalidate_pages();scene_allowed=value;if(!value){scene.invalidate();scene_ids.clear();}}
    // One bounded, single-use continuation session per view. The stack contains
    // only the active DFS path; pages are never published to SceneStream.
    QJsonObject scene_page(const QJsonObject &request) try {
        const auto op=request.value("op").toString();
        if(!scene_allowed){page_session.reset();return {{"status","DENIED"}};}
        if(!doc){page_session.reset();return {{"status","SEMANTICS_UNAVAILABLE"}};}
        if(op=="snapshot_begin"){
            const auto query=request.value("role").toString();
            const int limit=request.contains("maxNodes")?request.value("maxNodes").toInt(-1):16;
            if((!query.isEmpty() && query!="content" && query!="text" && query!="link") || limit<1 || limit>16)
                return {{"status","BAD_QUERY"}};
            // Never wrap the session counter within this provider instance.
            if(page_nonce==~quint64(0))return {{"status","RESOURCE_LIMIT"}};
            page_session.reset(new PageSession);
            auto &s=*page_session;s.query=query;s.visible=request.value("visibleOnly").toBool(false);s.limit=unsigned(limit);
            s.epoch=scene.source_epoch();s.revision=page_revision;s.age.start();page_expiry.start(30000);
            s.session_id=QString::number(++page_nonce);
            s.token=s.epoch+":"+s.session_id+":0";
            s.stack.append(PageFrame{doc->root(),0,0});
        }else{
            if(!page_session || request.value("cursor").toString()!=page_session->token)
                return {{"status","STALE_CURSOR"}};
            if(page_session->age.elapsed()>30000 || page_session->revision!=page_revision){page_session.reset();return {{"status","STALE_CURSOR"}};}
            if(op=="snapshot_cancel"){page_session.reset();return {{"status","CANCELLED"}};}
            if(op!="snapshot_next")return {{"status","BAD_REQUEST"}};
            if(request.contains("role") || request.contains("visibleOnly") || request.contains("maxNodes"))return {{"status","BAD_REQUEST"}};
        }
        auto &s=*page_session;QElapsedTimer timer;timer.start();QJsonArray nodes;int visited=0;
        const auto origin=viewport()->mapTo(window(),QPoint());const QRect view_rect(origin,viewport()->size());
        while(!s.stack.isEmpty() && visited<16 && nodes.size()<int(s.limit) && (visited==0 || timer.elapsed()<=30)){
            auto &f=s.stack.last();
            if(!f.entered){
                ++visited;f.entered=true;f.child=f.element->children().begin();
                if(f.depth>18){page_session.reset();return {{"status","RESOURCE_LIMIT"}};}
                const auto key=reinterpret_cast<quintptr>(f.element.get());
                if(!scene_ids.contains(key)){
                    if(scene_ids.size()>=4096){page_session.reset();return {{"status","RESOURCE_LIMIT"}};}
                    scene_ids[key]=next_scene_id++;
                }
                f.id=scene_ids[key];const auto *tag=f.element->get_tagName();const auto name=QString::fromUtf8(tag?tag:"");
                if(!s.query.isEmpty() && name=="head"){s.stack.removeLast();continue;}
                const bool matches=s.query.isEmpty() || (s.query=="content" && (f.element->is_text() || name=="a")) ||
                    (s.query=="link" && name=="a") || (s.query=="text" && f.element->is_text());
                if(!matches)continue;
                litehtml::position::vector boxes;const bool complete=f.element->get_rendering_fragments(boxes,8);QVector<QRect> local;
                for(const auto &box:boxes)local.append(QRect(box.x,box.y-verticalScrollBar()->value(),box.width,box.height).translated(origin));
                const auto g=scene_geometry(local,view_rect,complete);const auto b=g.bounds,c=g.visible_bounds;
                QJsonObject n{{"id",QString::number(f.id)},{"parent",QString::number(f.parent)},{"source","litehtml-model-and-render-layout"},
                    {"role",f.element->is_text()?"text":name=="a"?"link":"element"},{"tag",name},{"visibility",g.visibility},
                    {"fragments",g.fragments},{"visibleFragments",g.visible_fragments},{"fragmentsComplete",complete},
                    {"screenOcclusion","UNKNOWN_NO_COMPOSITOR"},{"bounds",QJsonArray{b.x(),b.y(),b.width(),b.height()}},
                    {"visibleBounds",QJsonArray{c.x(),c.y(),c.width(),c.height()}},
                    {"displayNone",f.element->css().get_display()==litehtml::display_none},{"contentTrust","untrusted-document-content"},
                    {"actionAuthority","READ_ONLY_NO_GRANT"}};
                if(f.element->is_text()){litehtml::string text;f.element->get_text(text);const auto q=QString::fromUtf8(text.c_str());
                    if(q.size()>1024){page_session.reset();return {{"status","RESOURCE_LIMIT"}};}n["text"]=q;n["textTruncated"]=false;n["textRange"]=QJsonArray{0,q.size()};}
                if(name=="a"){n["href"]=QString::fromUtf8(f.element->get_attr("href","")).left(256);n["actions"]=QJsonArray{"inspect","click"};n["execution"]="NOT_IMPLEMENTED";}
                if(!s.visible || !g.visible_fragments.isEmpty())nodes.append(n);
            }else if(f.child!=f.element->children().end()){
                auto child=*f.child++;const auto parent=f.id;const auto depth=f.depth+1;
                s.stack.append(PageFrame{child,parent,depth});
            }else s.stack.removeLast();
        }
        const bool complete=s.stack.isEmpty();const auto epoch=s.epoch;const auto revision=s.revision;const auto query=s.query;const auto visible=s.visible;
        const auto session_id=s.session_id;
        const auto seq=++s.sequence;const auto cursor=complete?QString():s.epoch+":"+session_id+":"+QString::number(seq);
        s.token=cursor;
        QJsonObject result{{"status","OK"},{"sourceEpoch",epoch},{"sourceRevision",QString::number(revision)},
            {"query",query},{"visibleOnly",visible},{"sessionId",session_id},{"pageSequence",QString::number(seq)},{"complete",complete},
            {"hasData",!nodes.isEmpty()},{"hasNext",!complete},{"sourceValid",true},
            {"traversalComplete",complete},{"stopReason",complete?"EXHAUSTED":"PAGE_BUDGET"},
            {"scrollY",verticalScrollBar()->value()},
            {"cursor",cursor},{"nodes",nodes},{"visited",visited},{"elapsedMs",QString::number(timer.elapsed())},
            {"baselineStatus",complete?"CONSUMER_MUST_VALIDATE":"INCOMPLETE"},{"diffStatus","RESET_REQUIRED_NO_PAGED_BASELINE"}};
        if(complete)page_session.reset();return result;
    }catch(const std::bad_alloc &){page_session.reset();return {{"status","RESOURCE_LIMIT"}};}
    QJsonObject scene_snapshot(const QString &query={},bool visible_only=false,unsigned node_limit=96) try {
        if(!scene_allowed)return {{"status","DENIED"}};
        if(!doc)return {{"status","SEMANTICS_UNAVAILABLE"}};
        if((!query.isEmpty() && query!="content" && query!="link" && query!="text") || node_limit<1 || node_limit>96)
            return {{"status","BAD_QUERY"}};
        QJsonArray nodes;int visited=0,text_left=8192,max_depth=0,text_truncated=0;bool capped=false;QElapsedTimer timer;timer.start();
        QString cap_reason="NONE";qint64 fragment_ms=0;
        const auto origin=viewport()->mapTo(window(),QPoint());
        const QRect view_rect(origin,viewport()->size());
        auto node_id=[&](const litehtml::element::ptr &e){const auto p=reinterpret_cast<quintptr>(e.get());if(!scene_ids.contains(p))scene_ids[p]=next_scene_id++;return scene_ids[p];};
        std::function<void(litehtml::element::ptr,quint64,int)> walk;
        walk=[&](litehtml::element::ptr e,quint64 parent,int depth){
            ++visited;max_depth=qMax(max_depth,depth);
            if(visited>96)cap_reason="VISITED_NODES";
            else if(nodes.size()>=int(node_limit))cap_reason="OUTPUT_NODES";
            else if(depth>18)cap_reason="DEPTH";
            else if(timer.elapsed()>30)cap_reason="TIME";
            if(cap_reason!="NONE"){capped=true;return;}
            const auto id=node_id(e);const auto *tag=e->get_tagName();const auto name=QString::fromUtf8(tag?tag:"");
            if(!query.isEmpty() && name=="head")return;
            const bool matches=query.isEmpty() || (query=="content" && (e->is_text() || name=="a")) ||
                (query=="link" && name=="a") || (query=="text" && e->is_text());
            if(!matches){for(auto &child:e->children()){walk(child,id,depth+1);if(capped)break;}return;}
            QElapsedTimer fragment_timer;fragment_timer.start();
            litehtml::position::vector boxes;const bool complete=e->get_rendering_fragments(boxes,8);QVector<QRect> local_boxes;
            for(const auto &box:boxes)local_boxes.append(QRect(box.x,box.y-verticalScrollBar()->value(),box.width,box.height).translated(origin));
            const auto geometry=scene_geometry(local_boxes,view_rect,complete);
            fragment_ms+=fragment_timer.elapsed();
            const auto bounds=geometry.bounds,clipped=geometry.visible_bounds;
            QJsonObject n{{"id",QString::number(id)},{"parent",QString::number(parent)},{"source","litehtml-model-and-render-layout"},
                {"role",e->is_text()?"text":name=="a"?"link":"element"},{"tag",name},{"visibility",geometry.visibility},
                {"fragments",geometry.fragments},{"visibleFragments",geometry.visible_fragments},
                {"fragmentsComplete",complete},{"screenOcclusion","UNKNOWN_NO_COMPOSITOR"},
                {"bounds",QJsonArray{bounds.x(),bounds.y(),bounds.width(),bounds.height()}},
                {"visibleBounds",QJsonArray{clipped.x(),clipped.y(),clipped.width(),clipped.height()}},
                {"displayNone",e->css().get_display()==litehtml::display_none},{"contentTrust","untrusted-document-content"},
                {"actionAuthority","READ_ONLY_NO_GRANT"}};
            if(e->is_text()){litehtml::string text;e->get_text(text);const auto q=QString::fromUtf8(text.c_str());const auto value=q.left(qMin(1024,text_left));n["text"]=value;n["textTruncated"]=value.size()!=q.size();if(value.size()!=q.size())++text_truncated;n["textRange"]=QJsonArray{0,value.size()};text_left-=value.size();}
            if(name=="a"){n["href"]=QString::fromUtf8(e->get_attr("href","")).left(256);n["actions"]=QJsonArray{"inspect","click"};n["execution"]="NOT_IMPLEMENTED";}
            if(!visible_only || !geometry.visible_fragments.isEmpty())nodes.append(n);
            for(auto &child:e->children()){walk(child,id,depth+1);if(capped)break;}
        };
        walk(doc->root(),0,0);
        const auto traversal_ms=timer.elapsed();
        QString hit="NONE";if(auto actual=doc->get_over_element()){const auto key=reinterpret_cast<quintptr>(actual.get());hit=scene_ids.contains(key)?QString::number(scene_ids[key]):"OUTSIDE_SNAPSHOT";}
        const QJsonObject scope{{"provider","litehtml-v0.9-ssg-readonly"},{"document",page},{"query",query},
            {"visibleOnly",visible_only},{"nodeLimit",int(node_limit)}};
        QElapsedTimer publish_timer;publish_timer.start();
        auto result=scene.publish(nodes,{{"provider","litehtml-v0.9-ssg-readonly"},{"document",page},{"query",query},{"queryScope",scope},{"scrollY",verticalScrollBar()->value()},
            {"viewport",QJsonArray{view_rect.x(),view_rect.y(),view_rect.width(),view_rect.height()}},{"hitNode",hit},
            {"hitSource","actual-engine-mouse-state"},{"iframes","UNSUPPORTED"},{"shadowDOM","UNSUPPORTED"},
            {"forms","UNSUPPORTED"},{"globalScene","BLOCKED"},{"subscriptions","NOT_IMPLEMENTED"}},capped);
        const auto publish_ms=publish_timer.elapsed();
        // Diagnostic fields are outside SceneStream's retained state so they do
        // not cause spurious versions or change the query scope. Millisecond
        // readings are quantized and per-node fragment samples can round down.
        result["diagnostics"]=QJsonObject{{"visitedAttempts",visited},{"outputNodes",int(nodes.size())},
            {"maxDepthAttempted",max_depth},{"depthLimit",18},{"visitedLimit",96},{"outputLimit",int(node_limit)},
            {"textBudgetUtf16",8192},{"textRemainingUtf16",text_left},{"textNodesTruncated",text_truncated},
            {"encodedNodesBytes",int(QJsonDocument(nodes).toJson(QJsonDocument::Compact).size())},{"encodedNodesLimitBytes",65536},
            {"timeLimitMs",30},{"capReason",cap_reason},{"traversalElapsedMs",QString::number(traversal_ms)},
            {"fragmentElapsedMsSum",QString::number(fragment_ms)},{"publishElapsedMs",QString::number(publish_ms)},
            {"clockResolution","millisecond-or-coarser; per-node samples may round down"},
            {"documentMutationDuringQuery","UNKNOWN_NO_INDEPENDENT_REVISION"},
            {"guiEventLoop","synchronous-query; responsiveness not measured"}};
        result["queryDurationNs"]=QString::number(timer.nsecsElapsed());return result;
    } catch(const std::bad_alloc &) {return {{"status","RESOURCE_LIMIT"}};}
    QJsonObject scene_diff(quint64 since,const QString &epoch)const{return scene.diff(since,epoch);}
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
