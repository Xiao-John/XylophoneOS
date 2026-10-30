// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "baseline.hpp"
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
namespace ssg_pipe {
enum class DiffStatus { ok, reset_required, resource_limit };
struct Change { std::string kind, id, before, after; };
struct Diff { DiffStatus status=DiffStatus::reset_required; std::vector<Change> changes; bool geometry_complete=true; };
inline bool equal_array(const std::string &a,const std::string &b) {
    return QJsonDocument::fromJson(QByteArray::fromStdString(a)).array()==QJsonDocument::fromJson(QByteArray::fromStdString(b)).array();
}
inline std::string geometry_value(const BaselineNode &n, bool visible) {
    QJsonObject o;
    if(visible){o["visibility"]=QString::fromStdString(n.visibility);o["visibleBounds"]=QJsonDocument::fromJson(QByteArray::fromStdString(n.visible_bounds)).array();o["visibleFragments"]=QJsonDocument::fromJson(QByteArray::fromStdString(n.visible_fragments)).array();}
    else {o["bounds"]=QJsonDocument::fromJson(QByteArray::fromStdString(n.bounds)).array();o["fragments"]=QJsonDocument::fromJson(QByteArray::fromStdString(n.fragments)).array();}
    return QJsonDocument(o).toJson(QJsonDocument::Compact).toStdString();
}
inline Diff compare_baselines(const Baseline &a,const Baseline &b) {
    Diff d;
    if(!a.traversal_complete || !a.locally_consistent || !b.traversal_complete || !b.locally_consistent ||
       a.instance!=b.instance || a.epoch!=b.epoch || a.session.empty() || b.session.empty() || a.session==b.session ||
       a.scope!=b.scope || a.visible_only!=b.visible_only || a.nodes.size()!=b.nodes.size())return d;
    // Scoped to an unchanged document: require the complete preorder identity and
    // parent/role/tag mapping to agree before reporting any per-node changes.
    for(size_t i=0;i<a.nodes.size();++i){const auto &x=a.nodes[i], &y=b.nodes[i];
        if(x.id!=y.id || x.parent!=y.parent || x.role!=y.role || x.tag!=y.tag)return d;
    }
    d.status=DiffStatus::ok;
    auto add=[&](const char *kind,const std::string &id,const std::string &before,const std::string &after){
        if(d.changes.size()>=32768){d.status=DiffStatus::resource_limit;d.changes.clear();return false;}
        d.changes.push_back({kind,id,before,after});return true;};
    if(a.scroll!=b.scroll && !add("ScrollChanged","",std::to_string(a.scroll),std::to_string(b.scroll)))return d;
    for(size_t i=0;i<a.nodes.size();++i){const auto &x=a.nodes[i], &y=b.nodes[i];
        if(x.has_text!=y.has_text || x.has_href!=y.has_href){d.status=DiffStatus::reset_required;d.changes.clear();return d;}
        if(x.has_text && x.text!=y.text && !add("TextChanged",x.id,x.text,y.text))return d;
        if(x.has_href && x.href!=y.href && !add("HrefChanged",x.id,x.href,y.href))return d;
        if(!x.geometry_known || !y.geometry_known || !x.fragments_complete || !y.fragments_complete)d.geometry_complete=false;
        if(x.geometry_known && y.geometry_known){
            if((!equal_array(x.fragments,y.fragments) || !equal_array(x.bounds,y.bounds)) && !add("WindowGeometryChanged",x.id,geometry_value(x,false),geometry_value(y,false)))return d;
            if((x.visibility!=y.visibility || !equal_array(x.visible_fragments,y.visible_fragments) || !equal_array(x.visible_bounds,y.visible_bounds)) && !add("VisibilityChanged",x.id,geometry_value(x,true),geometry_value(y,true)))return d;
        }
    }
    return d;
}
}
