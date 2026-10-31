// SPDX-License-Identifier: Apache-2.0
// Synthetic provider exercises the generic contract, not any WebKit API.
#include "../../../src/user/ssg/provider_contract.hpp"
#include "../../../src/user/ssg/watch_service.hpp"
#include "../../../src/user/ssg/capped_retry.hpp"
#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <cstdio>
using namespace ssg_watch;
struct test_payload final:provider_payload {int value;explicit test_payload(int v):value(v){}};
class test_provider final:public provider_adapter {
public:
    bool cancelled=false,force_unknown=false;observation next;watch_control *stop_control=nullptr;unsigned observations=0,stop_at=0;
    observation observe(uint64_t)override{if(++observations==stop_at && stop_control)stop_control->request_stop();return next;}
    bool available()override{return true;}
    void cancel()override{cancelled=true;}
    comparison compare(const observation &a,const observation &b)const override{
        if(force_unknown)return {"SOURCE_UNKNOWN",{{"reason","INCOMPLETE"}}};
        const int x=static_cast<const test_payload &>(*a.payload).value,y=static_cast<const test_payload &>(*b.payload).value;
        return {x==y?QStringLiteral("SOURCE_UNCHANGED"):QStringLiteral("SOURCE_CHANGED"),{{"value_before",x},{"value_after",y}}};
    }
};
struct alternate_payload final:provider_payload {int value=0;};
class alternate_provider final:public provider_adapter {
public:
    observation next;bool cancelled=false;
    observation observe(uint64_t)override{return next;}
    bool available()override{return true;}
    void cancel()override{cancelled=true;}
    comparison compare(const observation &a,const observation &b)const override{
        const auto &x=static_cast<const alternate_payload &>(*a.payload),&y=static_cast<const alternate_payload &>(*b.payload);
        return {x.value==y.value?QStringLiteral("SOURCE_UNCHANGED"):QStringLiteral("SOURCE_CHANGED"),{{"value_after",y.value}}};
    }
};
class stop_after_two final:public watch_hooks {
    watch_control &control_;
public:
    explicit stop_after_two(watch_control &control):control_(control){}
    bool cycle_complete(unsigned cycle)override{if(cycle==2)control_.request_stop();return true;}
};
static observation sample(const char *instance,const char *epoch,const char *revision,int value){
    observation o;o.slot="source";o.instance=instance;o.epoch=epoch;o.revision=revision;o.scope="whole";o.presentation="hidden";
    o.status="OBSERVED_COMPLETE";o.completeness="COMPLETE";o.freshness="UNVERIFIED_AFTER_OBSERVATION";
    o.capabilities={{"structure","SUPPORTED"},{"geometry","UNSUPPORTED"}};o.started_ns=10;o.ended_ns=20;
    o.payload=std::make_shared<test_payload>(value);return o;
}
int main(int argc,char **argv){
    QCoreApplication app(argc,argv);int checks=0,failures=0;
    auto check=[&](const char *name,bool pass){++checks;if(!pass)++failures;std::printf("P3C_CONTRACT_CHECK %s=%s\n",name,pass?"PASS":"FAIL");};
    test_provider adapter;watch_slot slot("source","i1");auto a=sample("i1","e1","r1",1);
    auto event=slot.accept(adapter,a);check("initial_baseline_unknown",event.value("event_type")=="SOURCE_UNKNOWN" && event.value("sequence")=="1");
    event=slot.accept(adapter,a);check("unchanged",event.value("event_type")=="SOURCE_UNCHANGED" && event.value("sequence")=="2");
    auto b=sample("i1","e1","r2",2);event=slot.accept(adapter,b);
    check("changed",event.value("event_type")=="SOURCE_CHANGED" && event.value("source_revision_before")=="r1" && event.value("source_revision_after")=="r2");
    check("unsupported_geometry",event.value("capability_set").toObject().value("geometry")=="UNSUPPORTED" && !event.value("summary").toObject().contains("geometry_changes"));
    auto denied=b;denied.status="DENIED";denied.failure_reason="DENIED";denied.payload.reset();denied.revision.clear();denied.epoch.clear();
    event=slot.accept(adapter,denied);check("permission_change",event.value("event_type")=="PERMISSION_CHANGED" && event.value("baseline_state")=="HISTORICAL_OR_ABSENT");
    event=slot.accept(adapter,denied);check("denial_not_unchanged",event.value("event_type")=="SOURCE_UNKNOWN");
    event=slot.accept(adapter,b);check("grant_reacquires",event.value("event_type")=="PERMISSION_CHANGED" && event.value("summary").toObject().value("baseline_reacquired")==true);
    auto unavailable=b;unavailable.status="UNAVAILABLE";unavailable.payload.reset();unavailable.epoch.clear();unavailable.revision.clear();
    event=slot.accept(adapter,unavailable);check("exit_unavailable",event.value("event_type")=="SOURCE_UNAVAILABLE");
    event=slot.accept(adapter,unavailable);check("exit_not_unchanged",event.value("event_type")=="SOURCE_UNAVAILABLE");
    event=slot.accept(adapter,b);check("recovery_requires_reset",event.value("event_type")=="RESET_REQUIRED");
    auto invalidated=b;invalidated.status="INVALIDATED";invalidated.payload.reset();invalidated.revision.clear();invalidated.epoch.clear();
    event=slot.accept(adapter,invalidated);check("invalidated_not_unchanged",event.value("event_type")=="SOURCE_INVALIDATED");
    event=slot.accept(adapter,b);check("invalidated_reacquire_reset",event.value("event_type")=="RESET_REQUIRED");
    check("rewire_requires_new_instance",!slot.rewire("i1") && slot.rewire("i2"));
    auto replacement=sample("i2","e1","r1",9);event=slot.accept(adapter,replacement);
    check("new_instance_replaced",event.value("event_type")=="SOURCE_REPLACED" && event.value("identity_namespace").toObject()==QJsonObject{{"slot","source"},{"source_instance","i2"},{"source_epoch","e1"}});
    replacement.epoch="e2";event=slot.accept(adapter,replacement);check("new_epoch_replaced",event.value("event_type")=="SOURCE_REPLACED");
    replacement.scope="other";event=slot.accept(adapter,replacement);check("scope_requires_reset",event.value("event_type")=="RESET_REQUIRED");
    replacement.slot="forged";event=slot.accept(adapter,replacement);check("slot_is_prewired",event.value("event_type")=="SOURCE_UNKNOWN" && event.value("slot")=="source" && event.value("completeness")=="NOT_OBSERVED");
    watch_slot unknown_slot("source","i1");unknown_slot.accept(adapter,a);adapter.force_unknown=true;
    event=unknown_slot.accept(adapter,b);check("unknown_comparison_invalidates",event.value("event_type")=="SOURCE_UNKNOWN" && event.value("baseline_state")=="HISTORICAL_OR_ABSENT");
    adapter.force_unknown=false;event=unknown_slot.accept(adapter,b);check("unknown_requires_new_baseline",event.value("event_type")=="RESET_REQUIRED");
    watch_slot replacement_denied("source","i1");replacement_denied.accept(adapter,a);replacement_denied.rewire("i2");
    auto denied_new=denied;denied_new.instance="i2";event=replacement_denied.accept(adapter,denied_new);
    check("replacement_precedes_denial",event.value("event_type")=="SOURCE_REPLACED" && event.value("baseline_state")=="HISTORICAL_OR_ABSENT");
    watch_control control;check("stop_initially_clear",!control.stopped());control.request_stop();adapter.cancel();check("explicit_stop_and_cancel",control.stopped() && adapter.cancelled);
    test_provider first;alternate_provider alternate;first.next=sample("i1","e1","r1",1);
    alternate.next=sample("i9","e9","r9",0);alternate.next.slot="alternate";alternate.next.payload=std::make_shared<alternate_payload>();
    watch_slot first_slot("source","i1"),alternate_slot("alternate","i9");watch_control loop_control;stop_after_two hooks(loop_control);
    const auto outcome=run_watch_loop(first,alternate,first_slot,alternate_slot,loop_control,{1,10,3,1},hooks);
    check("substituted_provider_uses_same_loop",outcome.output_ok && outcome.cycles==2 && outcome.events==4 && !outcome.partial);
    alternate.cancel();check("substituted_provider_cancelled",alternate.cancelled && loop_control.stopped());
    watch_control stopped;stopped.request_stop();watch_hooks plain_hooks;
    const auto empty=run_watch_loop(first,alternate,first_slot,alternate_slot,stopped,{1,10,3,1},plain_hooks);
    check("stop_before_baseline_is_partial",empty.cycles==0 && empty.partial);
    test_provider interrupted;interrupted.next=sample("i1","e1","r1",1);watch_control interrupted_control;
    interrupted.stop_control=&interrupted_control;interrupted.stop_at=2;watch_slot interrupted_slot("source","i1"),other_slot("alternate","i9");
    const auto interrupted_result=run_watch_loop(interrupted,alternate,interrupted_slot,other_slot,interrupted_control,{1,10,3,1},plain_hooks);
    check("stop_during_next_cycle_is_partial",interrupted_result.cycles==1 && interrupted_result.partial);
    std::fflush(stdout);int descriptors[2]={-1,-1};const int saved=dup(1);
    const bool redirected=saved>=0 && pipe(descriptors)==0 && dup2(descriptors[1],1)==1;
    watch_control fresh;watch_outcome blocked;
    if(redirected)blocked=run_watch_loop(first,alternate,first_slot,alternate_slot,fresh,{1,10,3,1},plain_hooks);
    if(saved>=0){dup2(saved,1);close(saved);}
    if(descriptors[0]>=0)close(descriptors[0]);if(descriptors[1]>=0)close(descriptors[1]);
    check("redirected_sink_fails_closed",redirected && !blocked.output_ok && blocked.cycles==0);
    uint64_t fake_now=0;unsigned attempts=0,retries=0,logged=0;bool budget=false;
    const auto clock=[&]{return fake_now;};const auto pause=[&](uint64_t until){fake_now=until;};
    const auto log_retry=[&](unsigned){++logged;};const auto on_budget=[&]{budget=true;};
    bool retried=retry_capped_observation([&]{return ++attempts<3?observation_attempt::capped:observation_attempt::complete;},
        clock,pause,log_retry,on_budget,100000000ull,retries);
    check("capped_retry_recovers",retried && attempts==3 && retries==2 && logged==2 && !budget);
    fake_now=0;attempts=0;logged=0;budget=false;
    retried=retry_capped_observation([&]{++attempts;return observation_attempt::capped;},clock,pause,log_retry,on_budget,100000000ull,retries);
    check("capped_retry_is_bounded",!retried && attempts==3 && retries==2 && logged==2 && !budget);
    fake_now=0;attempts=0;logged=0;budget=false;
    retried=retry_capped_observation([&]{++attempts;return observation_attempt::failed;},clock,pause,log_retry,on_budget,100000000ull,retries);
    check("noncap_failure_is_not_retried",!retried && attempts==1 && retries==0 && logged==0);
    fake_now=0;attempts=0;logged=0;budget=false;
    retried=retry_capped_observation([&]{++attempts;return observation_attempt::capped;},clock,pause,log_retry,on_budget,10000000ull,retries);
    check("capped_retry_respects_deadline",!retried && attempts==1 && retries==0 && budget);
    auto retry_sample=sample("i1","e1","r1",1);retry_sample.retry_count=2;watch_slot retry_slot("source","i1");
    check("retry_count_in_event",retry_slot.accept(first,retry_sample).value("retry_count").toInt(-1)==2);
    std::printf("P3C_CONTRACT_DONE checks=%d failures=%d\n",checks,failures);return failures?1:0;
}
