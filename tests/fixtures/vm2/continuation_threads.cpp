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
extern "C" int xos_user_main(const startup_info*) {
    if (thread::enable()!=0) return 1;
    u64 tid=0, status=1;
    if (thread::create(tid,peer,nullptr)!=0) return 2;
    while (!__atomic_load_n(&started,__ATOMIC_ACQUIRE)) yield();
    request r{1,64,0xfffe,0,1024,0,0,0,0,0,0};
    const auto result=syscall(67,reinterpret_cast<u64>(&r));
    __atomic_store_n(&stop,1u,__ATOMIC_RELEASE);
    if (thread::join(tid,status)!=0 || status!=0 || result!=0) return 3;
    print("VM2_PEER_FROZEN_PASS\n"); return 0;
}
