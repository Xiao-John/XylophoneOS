// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
__thread u64 tls_probe=3;
u64 child_pid;
process_status* output_status;
u32* word;
u64 waiting_tid;
u64* joined_result;
u64 deadline;
u64 timed_waiter(void*) { return static_cast<u64>(thread::wait(word,0,deadline)); }
u64 word_waiter(void*) { return thread::wait(word,0)==0 ? 42 : 1; }
u64 join_waiter(void*) { return thread::join(waiting_tid,*joined_result)==0 ? 0 : 1; }
u64 waiter(void*) {
    if (tls_probe!=3 || wait(child_pid,*output_status)!=0) return 1;
    return output_status->outcome==process_outcome::killed ? 0 : 2;
}
extern "C" int xos_user_main(const startup_info* info) {
    if(thread::enable()!=0 || syscall(sys_heap_break,process_heap_begin+8192)<0) return 1;
    constexpr u64 base=0x100000000000ull;
    request region{1,64,1,1,base,8192,4096,0,0,0,0};
    if(syscall(67,reinterpret_cast<u64>(&region))!=static_cast<i64>(base))return 10;
    region.operation=2;region.flags=0;region.alignment=0;region.protection=3;
    if(syscall(67,reinterpret_cast<u64>(&region)))return 11;
    word=reinterpret_cast<u32*>(base); *word=0;
    const auto args=reinterpret_cast<const char* const*>(info->argv);
    if(info->argc>1 && equal(args[1],"closing")) {
        deadline=thread_deadline_infinite;
        u64 blocked=0;
        if(thread::create(blocked,timed_waiter,nullptr))return 23;
        for(u32 i=0;i<200;++i) {
            thread_stats stats{};
            if(syscall(sys_thread_stats,reinterpret_cast<u64>(&stats)))return 24;
            if(stats.waiting) { print("VM2_PIN_CLOSING_READY\n"); for(;;) yield(); }
            yield();
        }
        return 25;
    }
    output_status=reinterpret_cast<process_status*>(base+4096-16);
    const char* argv[]={"slow"};
    const auto child=spawn_file("/bin/slow.elf",1,argv);
    if(child<=0)return 2;
    child_pid=static_cast<u64>(child);
    u64 tid=0,value=1;
    if(thread::create(tid,waiter,nullptr)!=0)return 3;
    bool waiting=false;
    for(u32 i=0;i<100;++i) {
        thread_stats stats{};
        if(syscall(sys_thread_stats,reinterpret_cast<u64>(&stats))!=0)return 4;
        if(stats.waiting) { waiting=true;break; }
        yield();
    }
    if(!waiting)return 5;
    region.operation=3;region.protection=1;
    if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 12;
    region.operation=4;region.protection=0;
    if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 13;
    region.operation=5;
    if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 14;
    region.operation=3;region.protection=3;
    if(syscall(67,reinterpret_cast<u64>(&region)))return 15;
    request r{1,64,0xfffd,0,child_pid,reinterpret_cast<u64>(output_status),0,0,0,0,0};
    if(syscall(67,reinterpret_cast<u64>(&r))!=0)return 7;
    if(thread::join(tid,value)!=0 || value!=0)return 8;
    word=reinterpret_cast<u32*>(base); *word=0;
    joined_result=reinterpret_cast<u64*>(base+4096);
    u64 joiner=0;
    if(thread::create(waiting_tid,word_waiter,nullptr)!=0 ||
       thread::create(joiner,join_waiter,nullptr)!=0)return 17;
    bool both_waiting=false;
    for(u32 i=0;i<200;++i) {
        thread_stats stats{};
        if(syscall(sys_thread_stats,reinterpret_cast<u64>(&stats)))return 18;
        if(stats.waiting>=2) { both_waiting=true; break; }
        yield();
    }
    if(!both_waiting)return 19;
    region.operation=4;region.protection=0;region.length=4096;
    if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 20;
    region.address=base+4096;
    if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 21;
    if(thread::wake(word)!=1 || thread::join(joiner,value)!=0 || value!=0 || *joined_result!=42)return 22;
    for(u32 round=0;round<16;++round) {
        *word=0; deadline=thread::clock()+20*thread_tick_ns;
        u64 blocked=0;
        if(thread::create(blocked,timed_waiter,nullptr))return 26;
        bool pinned=false;
        for(u32 i=0;i<200;++i) {
            thread_stats stats{};
            if(syscall(sys_thread_stats,reinterpret_cast<u64>(&stats)))return 27;
            if(stats.waiting) { pinned=true; break; }
            yield();
        }
        if(!pinned)return 28;
        region.address=base;region.length=4096;region.operation=4;region.protection=0;
        if(syscall(67,reinterpret_cast<u64>(&region))!=-5)return 29;
        if(round&1) {
            if(thread::wake(word)!=1)return 30;
        } else if(thread::sleep_until(deadline+thread_tick_ns))return 31;
        if(thread::join(blocked,value))return 32;
        if(static_cast<i64>(value)!=((round&1) ? 0 : thread_error_timeout))return 33;
        if(syscall(67,reinterpret_cast<u64>(&region)))return 34;
        region.operation=2;region.protection=3;
        if(syscall(67,reinterpret_cast<u64>(&region)))return 35;
    }
    for(u32 round=0;round<16;++round) {
        *word=0; deadline=thread::clock()+20*thread_tick_ns;
        u64 blocked=0;
        if(thread::create(blocked,timed_waiter,nullptr))return 36;
        bool pinned=false;
        for(u32 i=0;i<200;++i) {
            thread_stats stats{};
            if(syscall(sys_thread_stats,reinterpret_cast<u64>(&stats)))return 37;
            if(stats.waiting) { pinned=true;break; }
            yield();
        }
        if(!pinned)return 38;
        const u64 target=(round&1) ? deadline : deadline-thread_tick_ns;
        if(thread::sleep_until(target))return 39;
        const i64 woke=thread::wake(word);
        if((woke!=0 && woke!=1) || thread::join(blocked,value))return 40;
        if(static_cast<i64>(value)!=(woke ? 0 : thread_error_timeout))return 41;
        region.address=base;region.length=4096;region.operation=4;region.protection=0;
        if(syscall(67,reinterpret_cast<u64>(&region)))return 42;
        region.operation=2;region.protection=3;
        if(syscall(67,reinterpret_cast<u64>(&region)))return 43;
    }
    print("VM2_PIN_TIMEOUT_WAKE_RACE_PASS\n");
    print("VM2_PIN_TIMEOUT_WAKE_PASS\n");
    region.operation=5;region.address=base;region.length=8192;region.protection=0;
    if(syscall(67,reinterpret_cast<u64>(&region)))return 16;
    if(syscall(sys_heap_break,process_heap_begin)<0)return 9;
    print("VM2_READY_CROSS_PAGE_PIN_PASS\n");return 0;
}
