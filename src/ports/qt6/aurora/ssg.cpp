// SPDX-License-Identifier: Apache-2.0
#include "ssg.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QElapsedTimer>
#include <QtCore/QJsonDocument>
#include <QtCore/QSet>
#include <QtWidgets/QAbstractButton>
#include <QtWidgets/QLabel>
#include <QtWidgets/QLineEdit>
#include <QtWidgets/QPlainTextEdit>
#include <QtWidgets/QScrollBar>
#include <QtGui/QTextCursor>
#include <QtGui/QTextDocument>
#include <functional>
#include <algorithm>
#include <new>
namespace aurora {
namespace {
quint32 epochs=0;
quint64 now_ns(){QElapsedTimer t;t.start();return quint64(t.msecsSinceReference())*1000000;}
QByteArray encode(const QJsonObject &o){return QJsonDocument(o).toJson(QJsonDocument::Compact);}
QJsonArray rect(const QRect &r){return {r.x(),r.y(),r.width(),r.height()};}
}
SceneStream::SceneStream():epoch((quint64(QCoreApplication::applicationPid())<<32)|++epochs){}
QString SceneStream::source_epoch() const{return QString::number(epoch);}
void SceneStream::invalidate(){epoch=(quint64(QCoreApplication::applicationPid())<<32)|++epochs;current={};previous={};version=0;}
QJsonObject SceneStream::publish(const QJsonArray &nodes,const QJsonObject &meta,bool capped) try {
    if(nodes.size()>128 || QJsonDocument(nodes).toJson(QJsonDocument::Compact).size()>65536 || encode(meta).size()>4096)
        return {{"status","RESOURCE_LIMIT"}};
    if(meta.contains("queryScope") && !meta["queryScope"].isObject())return {{"status","BAD_QUERY"}};
    QSet<QString> ids;
    for(const auto &value:nodes){
        if(!value.isObject())return {{"status","BAD_NODES"}};
        const QJsonValue id=value.toObject().value(QStringLiteral("id"));
        if(!id.isString() || id.toString().isEmpty() || ids.contains(id.toString()))return {{"status","BAD_NODES"}};
        ids.insert(id.toString());
    }
    QJsonObject stable{{"nodes",nodes},{"metadata",meta},{"capped",capped}};
    auto old=current;old.remove("observedMonotonicNs");old.remove("sceneVersion");old.remove("sourceEpoch");old.remove("version");old.remove("status");
    if(current.isEmpty() || encode(stable)!=encode(old)){previous=current;current=stable;++version;}
    current["version"]=1;current["status"]="OK";current["sceneVersion"]=QString::number(version);
    current["sourceEpoch"]=source_epoch();current["observedMonotonicNs"]=QString::number(now_ns());return current;
} catch(const std::bad_alloc &) {return {{"status","RESOURCE_LIMIT"}};}
QJsonObject SceneStream::diff(quint64 since,const QString &expected_epoch) const {
    if(current.isEmpty())return {{"status","UNAVAILABLE"}};
    QJsonObject result{{"version",1},{"sourceEpoch",source_epoch()},{"sceneVersion",QString::number(version)}};
    if(expected_epoch!=source_epoch()){result["status"]="SOURCE_REPLACED";return result;}
    result["metadata"]=current["metadata"];result["capped"]=current["capped"];
    result["removalMeaning"]="LEFT_QUERY_RESULT";
    // An incomplete traversal cannot establish which omitted nodes left the
    // result. Even an unchanged partial snapshot cannot certify a full diff.
    if(current["capped"].toBool()){result["status"]="RESET_REQUIRED";return result;}
    if(since==version){result["status"]="OK";result["changed"]=QJsonArray();result["removed"]=QJsonArray();return result;}
    if(previous.isEmpty() || previous["sceneVersion"].toString()!=QString::number(since)){result["status"]="RESET_REQUIRED";return result;}
    if(previous["capped"].toBool()){result["status"]="RESET_REQUIRED";return result;}
    const auto old_meta=previous["metadata"].toObject(),new_meta=current["metadata"].toObject();
    // Explicit scope permits mutable metadata (e.g. scroll position) to be
    // reported without treating it as a different query. Legacy publishers
    // without a scope conservatively require all metadata to match.
    if(old_meta.contains("queryScope") != new_meta.contains("queryScope") ||
       (old_meta.contains("queryScope") ? old_meta["queryScope"]!=new_meta["queryScope"] : old_meta!=new_meta)){
        result["status"]="RESET_REQUIRED";return result;
    }
    QJsonObject before,after;for(auto value:previous["nodes"].toArray()){auto n=value.toObject();before[n["id"].toString()]=n;}
    QJsonArray changed,removed;
    for(auto value:current["nodes"].toArray()){auto n=value.toObject();const auto id=n["id"].toString();after[id]=n;if(before[id]!=n)changed.append(n);}
    for(auto it=before.begin();it!=before.end();++it)if(!after.contains(it.key()))removed.append(it.key());
    result["status"]="OK";result["changed"]=changed;result["removed"]=removed;result["observedMonotonicNs"]=current["observedMonotonicNs"];return result;
}
void QtScene::host_allow_observation(bool read_text){permitted=true;text_permitted=read_text;identities.clear();stream.invalidate();}
void QtScene::revoke(){permitted=false;identities.clear();stream.invalidate();}
QJsonObject QtScene::snapshot(bool visible_only,const QString &requested_role) try {
    if(!permitted)return {{"status","DENIED"}};
    if(!root)return {{"status","SOURCE_DESTROYED"}};
    if(!node_limit)return {{"status","RESOURCE_LIMIT"}};
    if(requested_role.size()>32)return {{"status","BAD_QUERY"}};
    identities.erase(std::remove_if(identities.begin(),identities.end(),[](const Identity &i){return i.widget.isNull();}),identities.end());
    QJsonArray nodes;int text_budget=8192,visited=0;bool capped=false;QElapsedTimer timer;timer.start();
    auto identity=[&](QWidget *w){for(const auto &i:identities)if(i.widget==w)return i.id;if(identities.size()>=128)return quint64(0);identities.append({w,next_id++});return next_id-1;};
    std::function<void(QWidget*,quint64,int)> walk;
    walk=[&](QWidget *w,quint64 parent,int depth){
        if(++visited>128 || nodes.size()>=int(node_limit) || depth>12 || timer.elapsed()>30){capped=true;return;}
        const auto id=identity(w);if(!id){capped=true;return;}
        if(!requested_role.isEmpty()){
            const QString quick=qobject_cast<QLineEdit*>(w)?"textbox":qobject_cast<QPlainTextEdit*>(w)?"document":qobject_cast<QAbstractButton*>(w)?"button":qobject_cast<QLabel*>(w)?"label":qobject_cast<QScrollBar*>(w)?"scrollbar":"custom";
            if(quick!=requested_role){for(auto *child:w->children())if(auto *widget=qobject_cast<QWidget*>(child)){walk(widget,id,depth+1);if(capped)break;}return;}
        }
        QString role="custom",text,name=w->accessibleName();QJsonObject extra;
        bool sensitive=false;
        if(auto *line=qobject_cast<QLineEdit*>(w)){
            role="textbox";sensitive=line->echoMode()!=QLineEdit::Normal;
            if(!sensitive){text=line->text();extra["selectionStart"]=line->selectionStart();extra["selectionLength"]=line->selectedText().size();extra["readOnly"]=line->isReadOnly();}
        } else if(auto *edit=qobject_cast<QPlainTextEdit*>(w)){
            role="document";auto cursor=edit->textCursor();cursor.setPosition(0);cursor.setPosition(qMin(1024,edit->document()->characterCount()-1),QTextCursor::KeepAnchor);text=cursor.selectedText();text.replace(QChar::ParagraphSeparator,'\n');extra["documentLength"]=edit->document()->characterCount()-1;extra["selectionStart"]=edit->textCursor().selectionStart();extra["selectionEnd"]=edit->textCursor().selectionEnd();
            extra["scrollY"]=edit->verticalScrollBar()->value();extra["scrollMax"]=edit->verticalScrollBar()->maximum();extra["textScope"]="document-not-all-visible";
            extra["readOnly"]=edit->isReadOnly();
        } else if(auto *button=qobject_cast<QAbstractButton*>(w)){
            role="button";text=button->text();extra["checked"]=button->isChecked();extra["checkable"]=button->isCheckable();
        } else if(auto *label=qobject_cast<QLabel*>(w)){role="label";text=label->text();}
        else if(auto *scroll=qobject_cast<QScrollBar*>(w)){role="scrollbar";extra["value"]=scroll->value();extra["maximum"]=scroll->maximum();}
        const bool hidden=!w->isVisibleTo(root) || !root->isVisible();
        QRegion region=hidden?QRegion():w->visibleRegion();
        const auto geometry=QRect(w->mapTo(root,QPoint()),w->size());
        const auto visible=region.boundingRect().translated(geometry.topLeft()).intersected(root->rect());
        QJsonArray visible_fragments;for(const auto &fragment:region){if(visible_fragments.size()>=8)break;const auto clipped=fragment.translated(geometry.topLeft()).intersected(root->rect());if(!clipped.isEmpty())visible_fragments.append(rect(clipped));}
        const QString visibility=hidden?"hidden":visible.isEmpty()?"locally-occluded-or-clipped":"locally-visible";
        if((!visible_only || visibility=="locally-visible") && (requested_role.isEmpty() || role==requested_role)){
            QJsonArray actions;if(role=="textbox" && !sensitive){actions={"inspect","focus","select"};if(!extra["readOnly"].toBool())actions.append("set_text");}else if(role=="button")actions={"inspect","focus","activate"};else if(role=="document")actions={"inspect","focus","select","scroll"};
            QJsonObject n{{"id",QString::number(id)},{"parent",QString::number(parent)},{"role",role},{"name",name.left(128)},
                {"nativeName",w->objectName().left(128)},{"class",QString::fromLatin1(w->metaObject()->className()).left(64)},
                {"enabled",w->isEnabled()},{"focused",w->hasFocus()},{"visibility",visibility},{"bounds",rect(geometry)},
                {"visibleBounds",rect(visible)},{"visibleFragments",visible_fragments},{"fragmentsComplete",region.rectCount()<=8},{"source","qt-widget"},{"contentTrust","untrusted-application-content"},
                {"screenOcclusion","UNKNOWN_NO_COMPOSITOR"},{"sensitive",sensitive},{"actions",actions},
                {"actionAuthority","NOT_GRANTED_BY_OBSERVATION"},{"semantics",role=="custom"?"SEMANTICS_UNAVAILABLE":"native-structure"}};
            if(text_permitted && !sensitive){const auto bounded=text.left(qMin(1024,text_budget));n["text"]=bounded;n["textTruncated"]=bounded.size()!=text.size() || (role=="document" && extra["documentLength"].toInt()>bounded.size());text_budget-=bounded.size();}
            else n["textStatus"]=sensitive?"PROTECTED":"NOT_AUTHORIZED";
            if(!sensitive)for(auto it=extra.begin();it!=extra.end();++it)n[it.key()]=it.value();
            nodes.append(n);
        }
        for(auto *child:w->children())if(auto *widget=qobject_cast<QWidget*>(child)){walk(widget,id,depth+1);if(capped)break;}
    };
    walk(root,0,0);
    const QJsonObject query_scope{{"provider","qt-widget-v1"},{"scope","application-root"},{"textAuthorized",text_permitted},
        {"visibleOnly",visible_only},{"roleFilter",requested_role}};
    auto result=stream.publish(nodes,{{"provider","qt-widget-v1"},{"scope","application-root"},{"textAuthorized",text_permitted},
        {"visibleOnly",visible_only},{"roleFilter",requested_role},{"queryScope",query_scope},
        {"globalScene","BLOCKED"},{"subscriptions","NOT_IMPLEMENTED"}},capped);
    result["queryDurationNs"]=QString::number(timer.nsecsElapsed());return result;
} catch(const std::bad_alloc &) {return {{"status","RESOURCE_LIMIT"}};}
}
