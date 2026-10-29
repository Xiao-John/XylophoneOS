// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
using namespace xos;
namespace {
void number(u64 value) { char buffer[24]; u32 count=0; do {buffer[count++]=static_cast<char>('0'+value%10);value/=10;}while(value); while(count){char text[2]={buffer[--count],0};sdk::print(text);} }
void check(bool value,const char* name){if(!value){sdk::print("CLOCK_FAIL:");sdk::print(name);sdk::print("\n");sdk::exit(90);}}
}
extern "C" int xos_user_main(const startup_info*) {
    check(thread::enable()==0,"enable_thread_wait_profile");
    const u64 first=sdk::ticks();
    for(u32 i=0;i<4;++i){
        const u64 low=sdk::ticks(),ns=thread::clock(),high=sdk::ticks();
        check(ns%thread_tick_ns==0 && ns/thread_tick_ns>=low && ns/thread_tick_ns<=high,"sys7_sys46_single_source");
        const u64 deadline=ns+20000000;
        check(thread::sleep_until(deadline)==0 && thread::clock()>=deadline,"sleep_deadline");
    }
    u32 word=0;const u64 deadline=thread::clock()+20000000;
    check(thread::wait(&word,0,deadline)==thread_error_timeout && thread::clock()>=deadline,"word_wait_deadline");
    const i64 wall0=sdk::syscall(sys_clock_realtime);const u64 mono0=thread::clock();
    check(wall0>1700000000000000000ll,"independent_RTC_epoch");
    check(thread::sleep_until(mono0+30000000)==0,"RTC_elapsed_sleep");
    const i64 wall1=sdk::syscall(sys_clock_realtime);const u64 mono1=thread::clock();
    check(wall1>=wall0 && static_cast<u64>(wall1-wall0)+thread_tick_ns>=mono1-mono0 &&
          static_cast<u64>(wall1-wall0)<=mono1-mono0+thread_tick_ns,"RTC_uses_same_elapsed_source");
    sdk::print("CLOCK_USER_OK:first=");number(first);sdk::print(" last=");number(sdk::ticks());
    sdk::print(" wall=");number(static_cast<u64>(wall1));sdk::print("\n");return 0;
}
