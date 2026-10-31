// SPDX-License-Identifier: Apache-2.0
// Private, prewired observation contract. It grants no access by itself.
#pragma once
#include <QtCore/QJsonObject>
#include <QtCore/QString>
#include <cstdint>
#include <memory>

namespace ssg_watch {
struct provider_payload { virtual ~provider_payload() = default; };

struct observation {
    QString slot, instance, epoch, revision, scope, presentation;
    QString status, completeness, freshness, failure_reason;
    QJsonObject capabilities;
    uint64_t started_ns=0, ended_ns=0;
    unsigned retry_count=0;
    std::shared_ptr<const provider_payload> payload;
};

struct comparison {
    QString event_type; // SOURCE_CHANGED, SOURCE_UNCHANGED, RESET_REQUIRED, SOURCE_UNKNOWN
    QJsonObject summary; // bounded, non-sensitive adapter-specific counts or facts
};

// The trusted owner constructs each adapter with its prewired slot and instance.
// The interface deliberately knows no application, widget, or engine types.
class provider_adapter {
public:
    virtual ~provider_adapter() = default;
    virtual observation observe(uint64_t budget_ns)=0;
    virtual bool available()=0;
    virtual comparison compare(const observation &before,const observation &after) const=0;
    virtual void cancel()=0;
};

class watch_slot {
    QString slot_,instance_;
    uint64_t sequence_=0;
    bool has_previous_=false;
    observation previous_;
public:
    watch_slot(QString slot,QString instance):slot_(std::move(slot)),instance_(std::move(instance)){}
    const QString &name()const{return slot_;}
    bool complete(const observation &value)const{
        return value.slot==slot_ && value.instance==instance_ && value.status=="OBSERVED_COMPLETE" && value.payload &&
            value.ended_ns>=value.started_ns && !value.epoch.isEmpty() && !value.revision.isEmpty() &&
            !value.scope.isEmpty() && !value.presentation.isEmpty() && !value.capabilities.isEmpty() &&
            !value.completeness.isEmpty() && !value.freshness.isEmpty();
    }
    // Only the trusted supervisor may call this after establishing a new route.
    bool rewire(const QString &instance){if(instance.isEmpty() || instance==instance_)return false;instance_=instance;return true;}

    QJsonObject accept(provider_adapter &adapter,observation current){
        const auto old=previous_;
        if(current.slot!=slot_ || current.instance!=instance_ || current.ended_ns<current.started_ns ||
           current.scope.isEmpty() || current.presentation.isEmpty() || current.capabilities.isEmpty()){
            current.slot=slot_;current.instance=instance_;current.status="UNKNOWN";
            current.failure_reason="INVALID_OBSERVATION";current.payload.reset();current.epoch.clear();current.revision.clear();
            current.completeness="NOT_OBSERVED";current.freshness="NOT_CURRENT";
            if(current.scope.isEmpty())current.scope="UNKNOWN";
            if(current.presentation.isEmpty())current.presentation="UNKNOWN";
            if(current.capabilities.isEmpty())current.capabilities={{"unspecified","UNKNOWN"}};
        }
        if(current.status=="OBSERVED_COMPLETE" &&
           !complete(current)){
            current.status="UNKNOWN";current.failure_reason="INCOMPLETE_OBSERVATION";current.payload.reset();current.epoch.clear();current.revision.clear();
            current.completeness="NOT_OBSERVED";current.freshness="NOT_CURRENT";
        }
        QString kind,reason=current.failure_reason;
        QJsonObject summary;
        const bool restricted=current.status=="DENIED" || current.status=="PROTECTED";
        const bool old_restricted=has_previous_ && (old.status=="DENIED" || old.status=="PROTECTED");
        if(has_previous_ && old.instance!=current.instance){
            kind="SOURCE_REPLACED";
            if(current.status!="OBSERVED_COMPLETE"){current.payload.reset();summary["new_source_status"]=current.status;}
        } else if(restricted){
            kind=has_previous_ && (old.status=="OBSERVED_COMPLETE" || old_restricted) && old.status!=current.status
                ?"PERMISSION_CHANGED":"SOURCE_UNKNOWN";
            current.payload.reset();
        } else if(current.status=="UNAVAILABLE"){
            kind="SOURCE_UNAVAILABLE";current.payload.reset();
        } else if(current.status=="INVALIDATED"){
            kind="SOURCE_INVALIDATED";current.payload.reset();
        } else if(current.status!="OBSERVED_COMPLETE"){
            kind="SOURCE_UNKNOWN";current.payload.reset();
        } else if(!has_previous_){
            kind="SOURCE_UNKNOWN";reason="INITIAL_BASELINE";
        } else if(!old.epoch.isEmpty() && old.epoch!=current.epoch){
            kind="SOURCE_REPLACED";
        } else if(old_restricted){
            kind="PERMISSION_CHANGED";summary["baseline_reacquired"]=true;
        } else if(old.status!="OBSERVED_COMPLETE" || !old.payload){
            kind="RESET_REQUIRED";summary["baseline_reacquired"]=true;
        } else if(old.scope!=current.scope || old.presentation!=current.presentation || old.capabilities!=current.capabilities){
            kind="RESET_REQUIRED";reason="OBSERVATION_CONTRACT_CHANGED";
        } else {
            const auto result=adapter.compare(old,current);kind=result.event_type;summary=result.summary;
            if(kind!="SOURCE_CHANGED" && kind!="SOURCE_UNCHANGED" && kind!="RESET_REQUIRED" && kind!="SOURCE_UNKNOWN"){
                kind="SOURCE_UNKNOWN";reason="INVALID_COMPARISON";summary={};
            }
            // An unknown comparison breaks continuity. A later complete
            // observation must establish a new baseline before ordinary diff.
            if(kind=="SOURCE_UNKNOWN")current.payload.reset();
        }
        const QJsonObject identity_namespace{{"slot",slot_},{"source_instance",instance_},{"source_epoch",current.epoch}};
        QJsonObject event{{"slot",slot_},{"identity_namespace",identity_namespace},
            {"source_instance",instance_},{"source_epoch",current.epoch},
            {"source_revision_before",has_previous_?old.revision:QString{}},
            {"source_revision_after",current.revision},{"sequence",QString::number(++sequence_)},
            {"observation_start",current.ended_ns>=current.started_ns?QJsonValue(QString::number(current.started_ns)):QJsonValue(QJsonValue::Null)},
            {"observation_end",current.ended_ns>=current.started_ns?QJsonValue(QString::number(current.ended_ns)):QJsonValue(QJsonValue::Null)},
            {"observation_scope",current.scope},{"presentation_state",current.presentation},
            {"capability_set",current.capabilities},{"event_type",kind},
            {"retry_count",int(current.retry_count)},
            {"completeness",current.completeness},{"freshness",current.freshness},
            {"failure_reason",reason},{"summary",summary},
            {"baseline_state",current.status=="OBSERVED_COMPLETE" && current.payload?"CURRENT_OBSERVATION":"HISTORICAL_OR_ABSENT"}};
        previous_=std::move(current);has_previous_=true;
        return event;
    }
};

class watch_control {
    alignas(4) unsigned stopped_=0;
public:
    void request_stop(){__atomic_store_n(&stopped_,1u,__ATOMIC_RELEASE);}
    bool stopped()const{return __atomic_load_n(&stopped_,__ATOMIC_ACQUIRE)!=0;}
};
}
