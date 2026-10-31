// SPDX-License-Identifier: Apache-2.0
// Source-scoped comparison. Observation intervals and pagination sessions are
// deliberately not treated as content changes.
#pragma once
#include <QtCore/QJsonArray>
#include <QtCore/QJsonObject>
#include <QtCore/QString>

namespace ssg_multi {
inline QString source_change(QJsonObject before,QJsonObject after){
    const auto slot=before.value("slot").toString();
    if(slot.isEmpty() || after.value("slot").toString()!=slot)return "UNKNOWN";
    const auto a=before.value("status").toString(),b=after.value("status").toString();
    const auto restricted=[](const QString &s){return s=="DENIED" || s=="PROTECTED";};
    if(restricted(b) && a!=b)return "PERMISSION_CHANGED";
    if(b=="UNAVAILABLE" && a=="OBSERVED_COMPLETE")return "INVALIDATED";
    if(restricted(a) && b=="OBSERVED_COMPLETE")return "PERMISSION_CHANGED";
    if(a!="OBSERVED_COMPLETE" || b!="OBSERVED_COMPLETE")return "UNKNOWN";
    const auto ai=before.value("instance").toString(),bi=after.value("instance").toString();
    const auto ae=before.value("epoch").toString(),be=after.value("epoch").toString();
    if(ai.isEmpty() || bi.isEmpty() || ae.isEmpty() || be.isEmpty())return "UNKNOWN";
    if(ai!=bi || ae!=be)return "REPLACED";
    const auto scope=before.value("scope").toString(),presentation=before.value("presentation").toString();
    if(scope.isEmpty() || presentation.isEmpty() || after.value("scope").toString()!=scope || after.value("presentation").toString()!=presentation)return "UNKNOWN";
    if(slot=="browser"){
        if(!before.value("nodes").isArray() || !after.value("nodes").isArray() || before.value("nodes").toArray().isEmpty() || after.value("nodes").toArray().isEmpty() ||
           !before.value("scrollY").isDouble() || !after.value("scrollY").isDouble())return "UNKNOWN";
    } else if(slot=="notes"){
        const auto x=before.value("document").toObject(),y=after.value("document").toObject();
        if(!x.value("text").isString() || !y.value("text").isString() || before.value("revision").toString().isEmpty() || after.value("revision").toString().isEmpty())return "UNKNOWN";
    } else return "UNKNOWN";
    for(const auto &key:{"startedMonotonicNs","endedMonotonicNs","session"}){
        before.remove(QLatin1String(key));after.remove(QLatin1String(key));
    }
    if(before!=after)return "CHANGED";
    if(slot=="browser")for(const auto value:before.value("nodes").toArray())
        if(!value.isObject() || value.toObject().value("fragmentsComplete")!=true)return "UNKNOWN";
    return "UNCHANGED";
}
inline QJsonObject aggregate_diff(const QJsonObject &before,const QJsonObject &after){
    const auto old_sources=before.value("sources").toArray(),new_sources=after.value("sources").toArray();
    if(old_sources.size()!=2 || new_sources.size()!=2)return {{"status","UNKNOWN"}};
    QJsonObject result{{"status","OK"},{"semantics","per-source-non-atomic"}};
    for(const auto &slot:{"browser","notes"}){
        QJsonObject a,b;int old_count=0,new_count=0;
        for(const auto v:old_sources){const auto s=v.toObject();if(s.value("slot")==slot){a=s;++old_count;}}
        for(const auto v:new_sources){const auto s=v.toObject();if(s.value("slot")==slot){b=s;++new_count;}}
        result[slot]=old_count==1 && new_count==1?source_change(a,b):QStringLiteral("UNKNOWN");
    }
    return result;
}
}
