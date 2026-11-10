// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
constexpr u64 base=0x100000000000ull, page=4096;
static i64 call(request& r) { return syscall(67,reinterpret_cast<u64>(&r)); }
static int fail(const char* text) { print("VM2_PAGES_FAIL "); print(text); print("\n"); return 1; }
extern "C" int xos_user_main(const startup_info* info) {
 const auto argv=reinterpret_cast<const char* const*>(info->argv);
 if(info->argc>1 && equal(argv[1],"sweep")) {
  request r{1,64,1,1,base,4097*page,page,0,0,0,0};
  if(call(r)!=static_cast<i64>(base))return fail("sweep_reserve");
  r.operation=2;r.flags=0;r.address=base+4096*page;r.length=page;r.alignment=0;r.protection=3;
  if(call(r))return fail("sweep_sentinel_commit");
  auto* sentinel=reinterpret_cast<volatile u64*>(r.address); *sentinel=0x123456789abcdef0ull;
  request stats{1,64,0xffff,0,0,0,0,0,0,0,0};
  const i64 before=call(stats);
  request inject{1,64,0xfffc,0,0,0,0,0,0,0,0};
  r.address=base;r.length=4096*page;
  for(u32 n=0;n<4096;++n) {
   inject.address=n;
   if(call(inject) || call(r)!=-4 || call(stats)!=before || *sentinel!=0x123456789abcdef0ull) {
    print("VM2_SWEEP_FAILED_AT="); decimal(n); print("\n");return 1;
   }
   if((n&255)==255) { print("VM2_SWEEP_THROUGH="); decimal(n); print("\n"); }
  }
  r.operation=5;r.length=4097*page;r.protection=0;
  if(call(r))return fail("sweep_unmap");
  print("VM2_SWEEP_PASS\n"); return 0;
 }
 if(info->argc>1 && equal(argv[1],"kill")) {
  request large{1,64,1,1,base,4096*page,page,0,0,0,0};
  if(call(large)!=static_cast<i64>(base))return fail("kill_reserve");
  request trace{1,64,0xfffb,0,0,0,0,0,0,0,0};
  if(call(trace))return fail("kill_trace");
  large.operation=2;large.flags=0;large.alignment=0;large.protection=3;
  if(call(large))return fail("kill_commit");
  print("VM2_KILL_TRANSACTION_COMPLETE\n");return 0;
 }
 request r{1,64,1,1,base,128*page,page,0,0,0,0};
 request stats{1,64,0xffff,0,0,0,0,0,0,0,0};
 const i64 before=call(stats);
 if(call(r)!=static_cast<i64>(base))return fail("reserve");
 r.operation=2;r.flags=0;r.alignment=0;r.protection=3;
 if(info->argc==1) {
  request inject{1,64,0xfffc,1,0,0,0,0,0,0,0};
  for(u32 n=0;n<3;++n) {
   inject.address=n;if(call(inject) || call(r)!=-4 || call(stats)!=before)return fail("table_rollback");
  }
  inject.flags=0;
  for(u32 n=0;n<128;++n) {
   inject.address=n;if(call(inject) || call(r)!=-4 || call(stats)!=before)return fail("page_rollback");
  }
  r.length=page;
  if(call(r))return fail("mixed_setup");
  auto* preserved=reinterpret_cast<volatile u64*>(base);
  *preserved=0x123456789abcdef0ull;
  const i64 mixed_before=call(stats);
  inject.address=64;if(call(inject))return fail("mixed_inject");
  r.operation=3;r.length=128*page;r.protection=5;
  if(call(r)!=-4 || call(stats)!=mixed_before || *preserved!=0x123456789abcdef0ull)return fail("mixed_rollback");
  *preserved=7;
  r.operation=4;r.length=page;r.protection=0;
  if(call(r) || call(stats)!=before)return fail("mixed_cleanup");
  r.operation=2;r.length=128*page;r.protection=3;
 }
 if(call(r)!=0)return fail("commit");
 auto* p=reinterpret_cast<volatile u8*>(base);
 p[0]=0xb8;p[1]=42;p[2]=0;p[3]=0;p[4]=0;p[5]=0xc3;p[page+16]=91;
 if(info->argc>1) {
  if(equal(argv[1],"readwriteexec")) { print("VM2_FAULT_RW_EXEC\n"); return reinterpret_cast<int(*)()>(base)(); }
  if(equal(argv[1],"readwrite")) { r.operation=3;r.protection=1;if(call(r))return fail("read");print("VM2_FAULT_R_WRITE\n");p[0]=0; }
  if(equal(argv[1],"rxwrite")) { r.operation=3;r.protection=5;if(call(r))return fail("rx");print("VM2_FAULT_RX_WRITE\n");p[0]=0; }
  r.operation=3;r.protection=0;if(call(r))return fail("none");
  if(equal(argv[1],"noneread")) { print("VM2_FAULT_NONE_READ\n");return p[0]; }
  if(equal(argv[1],"nonewrite")) { print("VM2_FAULT_NONE_WRITE\n");p[0]=0; }
  if(equal(argv[1],"noneexec")) { print("VM2_FAULT_NONE_EXEC\n");return reinterpret_cast<int(*)()>(base)(); }
  return fail("missing_fault");
 }
 if(syscall(sys_random_bytes,base+page-8,16)!=0)return fail("cross_page_copyout");
 const char message[16]={'V','M','2','_','C','R','O','S','S','_','I','N','_','O','K','\n'};
 for(u32 i=0;i<16;++i)p[page-8+i]=static_cast<u8>(message[i]);
 if(syscall(1,base+page-8,16)!=16)return fail("cross_page_copyin");
 r.operation=3;r.protection=7;if(call(r)!=-3)return fail("wx");
 r.protection=5;if(call(r))return fail("rx");
 if(reinterpret_cast<int(*)()>(base)()!=42)return fail("rx_execute");
 r.protection=0;if(call(r))return fail("none");
 r.protection=3;if(call(r) || p[page+16]!=91)return fail("none_preserve");
 r.operation=4;r.protection=0;if(call(r))return fail("decommit");
 r.operation=2;r.protection=3;if(call(r) || p[0] || p[page+16])return fail("decommit_zero");
 r.operation=5;r.protection=0;if(call(r) || call(stats)!=before)return fail("unmap_reclaims");
 r.operation=1;r.flags=1;r.address=base;r.length=4ull<<40;r.alignment=1ull<<40;
 if(call(r)!=static_cast<i64>(base))return fail("large_reserve");
 r.operation=2;r.flags=0;r.address=base+(3ull<<40);r.length=page;r.alignment=0;r.protection=3;
 if(call(r))return fail("sparse_commit");
 r.operation=5;r.address=base;r.length=4ull<<40;r.protection=0;
 if(call(r) || call(stats)!=before)return fail("sparse_unmap");
 r.operation=1;r.flags=1;r.address=base;r.length=4097*page;r.alignment=page;
 if(call(r)!=static_cast<i64>(base))return fail("unmap_limit_reserve");
 r.operation=2;r.flags=0;r.length=4096*page;r.alignment=0;r.protection=3;
 if(call(r))return fail("unmap_limit_commit");
 r.address=base+4096*page;r.length=page;
 if(call(r))return fail("unmap_limit_tail");
 p[0]=37;*reinterpret_cast<volatile u8*>(r.address)=61;
 r.operation=5;r.address=base;r.length=4097*page;r.protection=0;
 if(call(r)!=-4 || p[0]!=37 || *reinterpret_cast<volatile u8*>(base+4096*page)!=61)
  return fail("unmap_limit_rollback");
 r.operation=4;r.address=base+4096*page;r.length=page;
 if(call(r))return fail("unmap_limit_decommit");
 r.operation=5;r.address=base;r.length=4097*page;
 if(call(r) || call(stats)!=before)return fail("unmap_limit_cleanup");
 print("VM2_PAGES_PASS\n");return 0;
}
