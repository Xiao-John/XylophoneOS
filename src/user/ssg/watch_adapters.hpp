// SPDX-License-Identifier: Apache-2.0
// Compatibility adapters for the existing, independently prewired providers.
#pragma once
#include "provider_contract.hpp"
#include "multi_source.hpp"
#include "baseline_diff.hpp"
#include "capped_retry.hpp"

namespace ssg_watch {
using alive_callback=bool (*)(void *);

struct browser_payload final:provider_payload {
    ssg_pipe::Baseline baseline;
    explicit browser_payload(const ssg_pipe::Baseline &value):baseline(value){}
};
struct notes_payload final:provider_payload {
    ssg_multi::NotesBaseline baseline;
    explicit notes_payload(const ssg_multi::NotesBaseline &value):baseline(value){}
};

class browser_provider final:public provider_adapter {
    ssg_multi::Client &client_;QString instance_;bool hidden_;alive_callback alive_;void *source_;
    observation blank()const{
        observation o;o.slot="browser";o.instance=instance_;o.scope="unfiltered-litehtml";
        o.presentation=hidden_?"hidden-test-no-surface-no-input":"visible-surface";
        o.capabilities={{"structure","SUPPORTED"},{"text","SCOPED"},{"geometry","LIMITED"},
                        {"scroll","SUPPORTED"},{"utf16_range","UNSUPPORTED"},{"change_push","UNSUPPORTED"}};
        return o;
    }
public:
    browser_provider(ssg_multi::Client &client,const char *instance,bool hidden,alive_callback alive,void *source)
        :client_(client),instance_(QString::fromLatin1(instance)),hidden_(hidden),alive_(alive),source_(source){}
    bool available()override{return alive_(source_);}
    void cancel()override{client_.cancel();}
    observation observe(uint64_t budget_ns)override{
        auto o=blank();o.started_ns=xos::thread::clock();
        if(!available()){o.status="UNAVAILABLE";o.failure_reason="SOURCE_EXITED";}
        else {
            client_.begin_observation(budget_ns);ssg_pipe::BaselineCollector collector;
            const bool ok=collect_baseline(client_,collector) && collector.commit();
            if(ok && available()){
                const auto &b=*collector.committed();o.epoch=QString::fromStdString(b.epoch);o.revision=QString::fromStdString(b.revision);
                o.payload=std::make_shared<browser_payload>(b);o.status="OBSERVED_COMPLETE";
                o.completeness="LOCALLY_COMPLETE_ORACLE_REQUIRED";o.freshness="UNVERIFIED_AFTER_OBSERVATION";
            } else {
                const bool live=available();
                o.status=!live || !client_.error().isEmpty()?"UNAVAILABLE":client_.status()=="DENIED"?"DENIED":
                         client_.status()=="STALE_CURSOR" || client_.status()=="RESET_REQUIRED"?"INVALIDATED":"UNKNOWN";
                o.failure_reason=!client_.error().isEmpty()?client_.error():!client_.status().isEmpty() && client_.status()!="OK"?client_.status():"COLLECTION_OR_LIVENESS";
            }
        }
        o.ended_ns=xos::thread::clock();
        if(o.status!="OBSERVED_COMPLETE"){o.completeness="NOT_OBSERVED";o.freshness="NOT_CURRENT";}
        return o;
    }
    comparison compare(const observation &before,const observation &after)const override{
        const auto &a=static_cast<const browser_payload &>(*before.payload).baseline;
        const auto &b=static_cast<const browser_payload &>(*after.payload).baseline;
        const auto diff=ssg_pipe::compare_baselines(a,b);
        if(diff.status!=ssg_pipe::DiffStatus::ok)return {"RESET_REQUIRED",{{"reason","BROWSER_DIFF_RESET"}}};
        if(!diff.geometry_complete)return {"SOURCE_UNKNOWN",{{"reason","INCOMPLETE_GEOMETRY"}}};
        int scroll=0,geometry=0,visibility=0,other=0;
        for(const auto &change:diff.changes){
            if(change.kind=="ScrollChanged")++scroll;
            else if(change.kind=="WindowGeometryChanged")++geometry;
            else if(change.kind=="VisibilityChanged")++visibility;
            else ++other;
        }
        return {diff.changes.empty()?QStringLiteral("SOURCE_UNCHANGED"):QStringLiteral("SOURCE_CHANGED"),
            {{"scroll_changes",scroll},{"geometry_changes",geometry},{"visibility_changes",visibility},{"other_changes",other},
             {"scroll_before",a.scroll},{"scroll_after",b.scroll}}};
    }
};

class notes_provider final:public provider_adapter {
    ssg_multi::Client &client_;QString instance_;bool hidden_;alive_callback alive_;void *source_;
    observation blank()const{
        observation o;o.slot="notes";o.instance=instance_;o.scope="document-range-UTF-16";
        o.presentation=hidden_?"hidden-session-no-surface-no-input":"visible-surface";
        o.capabilities={{"structure","DOCUMENT_ONLY"},{"text","SCOPED"},{"geometry","UNSUPPORTED"},
                        {"scroll","UNSUPPORTED"},{"utf16_range","SUPPORTED"},{"protection","SUPPORTED"},{"change_push","UNSUPPORTED"}};
        return o;
    }
public:
    notes_provider(ssg_multi::Client &client,const char *instance,bool hidden,alive_callback alive,void *source)
        :client_(client),instance_(QString::fromLatin1(instance)),hidden_(hidden),alive_(alive),source_(source){}
    bool available()override{return alive_(source_);}
    void cancel()override{client_.cancel();}
    observation observe(uint64_t budget_ns)override{
        auto o=blank();o.started_ns=xos::thread::clock();
        if(!available()){o.status="UNAVAILABLE";o.failure_reason="SOURCE_EXITED";}
        else {
            client_.begin_observation(budget_ns);ssg_multi::NotesBaseline b;QString failure;
            const auto deadline=budget_ns>~uint64_t{0}-o.started_ns?~uint64_t{0}:o.started_ns+budget_ns;
            const bool ok=retry_capped_observation([&]{
                bool capped=false;
                if(ssg_multi::collect_notes(client_,b,failure,false,false,&capped))return observation_attempt::complete;
                return capped?observation_attempt::capped:observation_attempt::failed;
            },[]{return xos::thread::clock();},[](uint64_t until){xos::thread::sleep_until(until);},
            [](unsigned count){std::printf("P3C_NOTES_RETRY reason=CAPPED retry=%u\n",count);},
            [&]{failure="SOURCE_BUDGET";},deadline,o.retry_count);
            if(ok && available()){
                o.epoch=b.epoch;o.revision=b.revision;o.payload=std::make_shared<notes_payload>(b);
                o.status="OBSERVED_COMPLETE";o.completeness="REVISION_CONSISTENT_OWNER_ORACLE_REQUIRED";
                o.freshness="UNVERIFIED_AFTER_OBSERVATION";
            } else {
                const bool live=available();
                o.status=!live || !client_.error().isEmpty() || failure=="SOURCE_BUDGET"?"UNAVAILABLE":(failure=="DENIED" || failure=="PROTECTED")?failure:
                         (failure=="RESET_REQUIRED" || failure=="RETRY_BUDGET" || failure=="MIXED_RANGE")?"INVALIDATED":"UNKNOWN";
                o.failure_reason=failure.isEmpty()?QStringLiteral("COLLECTION_OR_LIVENESS"):failure;
            }
        }
        o.ended_ns=xos::thread::clock();
        if(o.status!="OBSERVED_COMPLETE"){o.completeness="NOT_OBSERVED";o.freshness="NOT_CURRENT";}
        return o;
    }
    comparison compare(const observation &before,const observation &after)const override{
        const auto &a=static_cast<const notes_payload &>(*before.payload).baseline;
        const auto &b=static_cast<const notes_payload &>(*after.payload).baseline;
        if(a.node!=b.node || (a.revision==b.revision && a.text!=b.text))return {"RESET_REQUIRED",{{"reason","NOTES_IDENTITY_OR_REVISION"}}};
        const bool text_changed=a.text!=b.text,revision_changed=a.revision!=b.revision;
        return {text_changed || revision_changed?QStringLiteral("SOURCE_CHANGED"):QStringLiteral("SOURCE_UNCHANGED"),
                {{"text_changed",text_changed},{"revision_changed",revision_changed},
                 {"utf16_units_before",a.units},{"utf16_units_after",b.units}}};
    }
};
}
