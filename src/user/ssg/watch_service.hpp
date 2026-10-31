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
// Each console write is a bounded single syscall. The leading newline makes
// each record independently recognizable even among unrelated process logs.
inline bool write_event_record(const QByteArray &record){
    if(record.isEmpty() || record.size()>256)return false;
    return xos::sdk::write(1,record.constData(),unsigned(record.size()))==record.size();
}
inline bool emit_event_frame(const QJsonObject &event,unsigned sequence){
    const auto payload=QJsonDocument(event).toJson(QJsonDocument::Compact);
    if(payload.isEmpty() || payload.size()>8192 || std::fflush(stdout)!=0)return false;
    const auto encoded=payload.toBase64();const auto number=QByteArray::number(sequence);
    if(!write_event_record(QByteArray("\nP3C_EVENT_BEGIN ")+number+' '+QByteArray::number(payload.size())+' '+QByteArray::number(encoded.size())+'\n'))return false;
    for(int offset=0;offset<encoded.size();offset+=96){
        if(!write_event_record(QByteArray("\nP3C_EVENT_PART ")+number+' '+QByteArray::number(offset)+' '+encoded.mid(offset,96)+'\n'))return false;
    }
    return write_event_record(QByteArray("\nP3C_EVENT_END ")+number+'\n');
}
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
    if(!isatty(1) || xos::sdk::syscall(xos::sys_process_stdio,0,1)!=1){result.output_ok=false;return result;}
    if(options.interval_seconds<1 || options.interval_seconds>30 || options.duration_seconds<1 || options.duration_seconds>3600 ||
       options.max_cycles<1 || options.max_cycles>1024 || options.source_timeout_seconds<1 || options.source_timeout_seconds>300){
        result.output_ok=false;std::printf("P3C_WATCH_ERROR reason=INVALID_BOUNDS\n");return result;
    }
    const u64 deadline=result.started_ns+u64(options.duration_seconds)*1000000000ull;
    const auto start_record=QByteArray("\nP3C_WATCH_STARTED interval_s=")+QByteArray::number(options.interval_seconds)+
        " duration_s="+QByteArray::number(options.duration_seconds)+" max_cycles="+QByteArray::number(options.max_cycles)+
        " source_timeout_s="+QByteArray::number(options.source_timeout_seconds)+" globalAtomicSnapshot=NOT_IMPLEMENTED\n";
    if(std::fflush(stdout)!=0 || !write_event_record(start_record)){result.output_ok=false;return result;}
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
            if(!emit_event_frame(event,result.events+1)){result.output_ok=false;break;}
            ++result.events;
        }
        if(!result.output_ok)break;
        ++result.cycles;
        const auto cycle_record=QByteArray("\nP3C_CYCLE_READY cycle=")+QByteArray::number(result.cycles)+
            " aggregate="+(result.partial?"PARTIAL":"OBSERVED_COMPLETE")+'\n';
        if(!write_event_record(cycle_record)){result.output_ok=false;break;}
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
