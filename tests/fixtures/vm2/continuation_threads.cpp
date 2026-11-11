// SPDX-License-Identifier: Apache-2.0
#include <xos/thread_core.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
__thread u64 tls_probe=1;
u32 started=0, stop=0;
u64 peer(void*) {
    if (tls_probe!=1) return 7;
    __atomic_store_n(&started,1u,__ATOMIC_RELEASE);
    while (!__atomic_load_n(&stop,__ATOMIC_ACQUIRE)) { __asm__ volatile("" ::: "memory"); }
    return 0;
}
constexpr u64 arena=0x100000000000ull;
u32 ready_count=0, launch=0, operation=0;
i64 results[2];
u64 concurrent_vm(void* arg) {
    const u64 index=reinterpret_cast<u64>(arg);
    request r{1,64,operation,operation==1 ? 1u : 0u,arena,128*4096,
              operation==1 ? 4096u : 0u,operation==2 ? 3u : operation==3 ? 1u : 0u,0,0,0};
    __atomic_add_fetch(&ready_count,1u,__ATOMIC_RELEASE);
    while (!__atomic_load_n(&launch,__ATOMIC_ACQUIRE)) yield();
    results[index]=syscall(67,reinterpret_cast<u64>(&r));
    return 0;
}
bool race_operation(u32 op) {
    ready_count=0; launch=0; operation=op; results[0]=results[1]=-99;
    u64 first=0,second=0,a=1,b=1;
    if(thread::create(first,concurrent_vm,reinterpret_cast<void*>(0)) ||
       thread::create(second,concurrent_vm,reinterpret_cast<void*>(1)))return false;
    while (__atomic_load_n(&ready_count,__ATOMIC_ACQUIRE)!=2) yield();
    __atomic_store_n(&launch,1u,__ATOMIC_RELEASE);
    if(thread::join(first,a) || thread::join(second,b) || a || b)return false;
    return op==1 ? ((results[0]==static_cast<i64>(arena) && results[1]==-7) ||
                    (results[1]==static_cast<i64>(arena) && results[0]==-7)) :
                   results[0]==0 && results[1]==0;
}
extern "C" int xos_user_main(const startup_info*) {
    if (thread::enable()!=0) return 1;
    u64 tid=0, status=1;
    if (thread::create(tid,peer,nullptr)!=0) return 2;
    while (!__atomic_load_n(&started,__ATOMIC_ACQUIRE)) yield();
    request r{1,64,0xfffe,0,1024,0,0,0,0,0,0};
    const auto result=syscall(67,reinterpret_cast<u64>(&r));
    __atomic_store_n(&stop,1u,__ATOMIC_RELEASE);
    if (thread::join(tid,status)!=0 || status!=0 || result!=0) return 3;
    if (!race_operation(1) || !race_operation(2) || !race_operation(3) || !race_operation(5)) return 4;
    print("VM2_PEER_FROZEN_PASS\n"); print("VM2_CONCURRENT_VM_PASS\n"); return 0;
}
