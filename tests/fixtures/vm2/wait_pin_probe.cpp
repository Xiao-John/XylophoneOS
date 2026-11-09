// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
__thread u64 tls_probe=3;
u64 child_pid;
process_status* output_status;
u64 waiter(void*) {
    if (tls_probe!=3 || wait(child_pid,*output_status)!=0) return 1;
    return output_status->outcome==process_outcome::killed ? 0 : 2;
}
extern "C" int xos_user_main(const startup_info*) {
    if(thread::enable()!=0 || syscall(sys_heap_break,process_heap_begin+8192)<0) return 1;
    output_status=reinterpret_cast<process_status*>(process_heap_begin+4096-16);
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
    if(syscall(sys_heap_break,process_heap_begin)!=thread_error_busy)return 6;
    request r{1,64,0xfffd,0,child_pid,reinterpret_cast<u64>(output_status),0,0,0,0,0};
    if(syscall(67,reinterpret_cast<u64>(&r))!=0)return 7;
    if(thread::join(tid,value)!=0 || value!=0)return 8;
    if(syscall(sys_heap_break,process_heap_begin)<0)return 9;
    print("VM2_READY_CROSS_PAGE_PIN_PASS\n");return 0;
}
