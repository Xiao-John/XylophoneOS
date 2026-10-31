// SPDX-License-Identifier: Apache-2.0
// Browser's existing paged collector, shared by single- and dual-source clients.
#pragma once
#include "baseline.hpp"
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <xos/thread_core.hpp>
#include <cstdio>
using ssg_pipe::BaselineCollector;
using ssg_pipe::BaselinePage;
using ssg_pipe::BaselineNode;

// This mode is limited to the existing prewired read-only parent/child pipe.
template<class Client>
static bool collect_baseline(Client &client, BaselineCollector &collector, bool inject=false, bool *stale=nullptr){
    if(stale)*stale=false;
    collector.begin(); bool transport=false; QString cursor,instance; QJsonObject request{{"op","snapshot_begin"},{"maxNodes",8}};
    for(unsigned seq=1;seq<=BaselineCollector::max_pages;++seq){
        const auto r=client.request(request,&transport);
        if(transport && r.value("status")=="STALE_CURSOR"){
            collector.cancel(); if(stale)*stale=true;
            std::printf("SSG_RECOVERY_STALE discarded=1\n"); return false;
        }
        auto exact_bool=[&](const QJsonObject &o,const char *k){return o.value(k).isBool();};
        if(!transport || r.value("status")!="OK" || r.value("pageSequence").toString()!=QString::number(seq) ||
           !r.value("nodes").isArray() || !r.value("cursor").isString() || !r.value("query").isString() ||
           !exact_bool(r,"complete") || !exact_bool(r,"visibleOnly") || !exact_bool(r,"sourceValid") ||
           !exact_bool(r,"hasNext") || !exact_bool(r,"hasData") || !exact_bool(r,"traversalComplete")) {collector.cancel();return false;}
        const int scroll=r.value("scrollY").toInt(-1), visited=r.value("visited").toInt(-1);
        if(!r.value("scrollY").isDouble() || r.value("scrollY").toDouble()!=scroll || !r.value("visited").isDouble() || r.value("visited").toDouble()!=visited || visited<0 ||
           r.value("stopReason")!=(r.value("complete").toBool()?"EXHAUSTED":"PAGE_BUDGET")){collector.cancel();return false;}
        BaselinePage p; p.instance=r.value("sourceInstance").toString().toStdString();p.epoch=r.value("sourceEpoch").toString().toStdString();
        p.revision=r.value("sourceRevision").toString().toStdString();p.session=r.value("sessionId").toString().toStdString();
        p.scope=r.value("query").toString().toStdString();p.request_cursor=cursor.toStdString();p.cursor=r.value("cursor").toString().toStdString();
        p.sequence=seq;p.scroll=scroll;p.visited=unsigned(visited);p.visible_only=r.value("visibleOnly").toBool();p.complete=r.value("complete").toBool();
        p.source_valid=r.value("sourceValid").toBool();p.has_next=r.value("hasNext").toBool();p.has_data=r.value("hasData").toBool();p.traversal_complete=r.value("traversalComplete").toBool();
        for(const auto v:r.value("nodes").toArray()){
            if(!v.isObject()){collector.cancel();return false;} const auto n=v.toObject();
            if(!n.value("id").isString() || !n.value("parent").isString() || !n.value("role").isString() || !n.value("tag").isString() || n.value("source")!="litehtml-model-and-render-layout" ||
               !n.value("visibility").isString() || !n.value("fragmentsComplete").isBool()){collector.cancel();return false;}
            auto valid_rect=[](const QJsonValue &v){if(!v.isArray() || v.toArray().size()!=4)return false;for(const auto x:v.toArray())if(!x.isDouble())return false;return true;};
            auto valid_rects=[&](const QJsonValue &v){if(!v.isArray() || v.toArray().size()>8)return false;for(const auto x:v.toArray())if(!valid_rect(x))return false;return true;};
            if(!valid_rect(n.value("bounds")) || !valid_rect(n.value("visibleBounds")) || !valid_rects(n.value("fragments")) || !valid_rects(n.value("visibleFragments"))){collector.cancel();return false;}
            BaselineNode node;node.id=n.value("id").toString().toStdString();node.parent=n.value("parent").toString().toStdString();node.role=n.value("role").toString().toStdString();node.tag=n.value("tag").toString().toStdString();
            node.has_text=n.value("text").isString();node.has_href=n.value("href").isString();node.text=n.value("text").toString().toStdString();node.href=n.value("href").toString().toStdString();
            if(node.has_text && (n.value("textTruncated")!=false || n.value("text").toString().size()>1024 || n.value("textRange").toArray()!=QJsonArray{0,n.value("text").toString().size()})){collector.cancel();return false;}
            auto array=[&](const char *k){return QJsonDocument(n.value(k).toArray()).toJson(QJsonDocument::Compact).toStdString();};
            node.fragments=array("fragments");node.visible_fragments=array("visibleFragments");node.bounds=array("bounds");node.visible_bounds=array("visibleBounds");node.visibility=n.value("visibility").toString().toStdString();node.geometry_known=true;node.fragments_complete=n.value("fragmentsComplete").toBool();p.nodes.push_back(node);
        }
        if(!collector.accept(p))return false;
        if(p.complete)return true;
        if(inject && seq==3){
            std::printf("SSG_RECOVERY_INJECTION_READY pages=%u session=%s\n",seq,p.session.c_str());
            xos::thread::sleep_until(xos::thread::clock()+15000000000ull);
        }
        cursor=r.value("cursor").toString();instance=r.value("sourceInstance").toString();request={{"op","snapshot_next"},{"sourceInstance",instance},{"cursor",cursor}};
    }
    collector.cancel();return false;
}
