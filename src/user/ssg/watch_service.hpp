// SPDX-License-Identifier: Apache-2.0
// Engine- and application-independent, bounded sequential observation loop.
#pragma once
#include "provider_contract.hpp"
#include <QtCore/QJsonDocument>
#include <xos/thread_core.hpp>
#include <cstdio>
#include <unistd.h>

namespace ssg_watch {
struct watch_options {
    unsigned interval_seconds=5,duration_seconds=120,max_cycles=12,source_timeout_seconds=60;
};
struct watch_outcome {
    uint64_t started_ns=0,elapsed_ns=0;
    unsigned cycles=0,events=0;
    bool output_ok=true,partial=true;
};
class watch_hooks {
public:
    virtual ~watch_hooks()=default;
    virtual void observation_started(unsigned,unsigned){}
    virtual bool observations_ready(unsigned,const observation &,const observation &){return true;}
    virtual bool cycle_complete(unsigned){return true;}
};
inline void recheck_provider(provider_adapter &provider,observation &o){
    if(!provider.available()){
        o.status="UNAVAILABLE";o.failure_reason="SOURCE_EXITED";o.completeness="NOT_OBSERVED";
        o.freshness="NOT_CURRENT";o.epoch.clear();o.revision.clear();o.payload.reset();
        o.ended_ns=xos::thread::clock();
    }
}
inline watch_outcome run_watch_loop(provider_adapter &first,provider_adapter &second,
                                    watch_slot &first_slot,watch_slot &second_slot,
                                    watch_control &control,const watch_options &options,watch_hooks &hooks){
    using xos::u64;
    watch_outcome result;result.started_ns=xos::thread::clock();
    // Newlib's pipe-backed stdout can block without a deadline. Until an
    // independently bounded sink exists, do not start on redirected stdout.
    if(!isatty(1)){result.output_ok=false;return result;}
    if(options.interval_seconds<1 || options.interval_seconds>30 || options.duration_seconds<1 || options.duration_seconds>3600 ||
       options.max_cycles<1 || options.max_cycles>1024 || options.source_timeout_seconds<1 || options.source_timeout_seconds>300){
        result.output_ok=false;std::printf("P3C_WATCH_ERROR reason=INVALID_BOUNDS\n");return result;
    }
    const u64 deadline=result.started_ns+u64(options.duration_seconds)*1000000000ull;
    std::printf("P3C_WATCH_STARTED interval_s=%u duration_s=%u max_cycles=%u source_timeout_s=%u globalAtomicSnapshot=NOT_IMPLEMENTED\n",
                options.interval_seconds,options.duration_seconds,options.max_cycles,options.source_timeout_seconds);
    while(result.cycles<options.max_cycles && !control.stopped()){
        auto now=xos::thread::clock();if(now>=deadline)break;
        const u64 first_budget=qMin(u64(options.source_timeout_seconds)*1000000000ull,deadline-now);
        std::printf("P3C_OBSERVE_BEGIN slot=%s cycle=%u\n",first_slot.name().toUtf8().constData(),result.cycles+1);
        hooks.observation_started(0,result.cycles+1);
        auto a=first.observe(first_budget);if(control.stopped()){result.partial=true;break;}
        now=xos::thread::clock();if(now>=deadline){result.partial=true;break;}
        const u64 second_budget=qMin(u64(options.source_timeout_seconds)*1000000000ull,deadline-now);
        std::printf("P3C_OBSERVE_BEGIN slot=%s cycle=%u\n",second_slot.name().toUtf8().constData(),result.cycles+1);
        hooks.observation_started(1,result.cycles+1);
        auto b=second.observe(second_budget);if(control.stopped()){result.partial=true;break;}
        recheck_provider(first,a);recheck_provider(second,b);
        result.partial=!first_slot.complete(a) || !second_slot.complete(b);
        if(!hooks.observations_ready(result.cycles+1,a,b)){result.output_ok=false;break;}
        const auto a_event=first_slot.accept(first,std::move(a));
        const auto b_event=second_slot.accept(second,std::move(b));
        for(const auto &event:{a_event,b_event}){
            const auto bytes=QJsonDocument(event).toJson(QJsonDocument::Compact);
            if(bytes.size()>8192 || std::printf("P3C_EVENT %s\n",bytes.constData())<0 || std::fflush(stdout)!=0){result.output_ok=false;break;}
            ++result.events;
        }
        if(!result.output_ok)break;
        ++result.cycles;
        std::printf("P3C_CYCLE_READY cycle=%u aggregate=%s\n",result.cycles,result.partial?"PARTIAL":"OBSERVED_COMPLETE");
        if(!hooks.cycle_complete(result.cycles)){result.output_ok=false;break;}
        if(result.cycles==options.max_cycles)break;
        const u64 next=qMin(deadline,xos::thread::clock()+u64(options.interval_seconds)*1000000000ull);
        while(!control.stopped() && xos::thread::clock()<next)
            xos::thread::sleep_until(qMin(next,xos::thread::clock()+100000000ull));
    }
    result.elapsed_ns=xos::thread::clock()-result.started_ns;
    return result;
}
}
