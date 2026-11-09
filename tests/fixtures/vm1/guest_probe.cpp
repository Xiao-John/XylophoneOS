// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
using namespace xos;
using namespace xos::sdk;
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
static_assert(sizeof(request)==64);
constexpr u64 base=0x100000000000ull, page=4096, end=0x200000000000ull;
static i64 call(request& r) { return syscall(67,reinterpret_cast<u64>(&r)); }
static int fail(const char* name) { print("VM1_FAIL "); print(name); print("\n"); return 1; }
extern "C" int xos_user_main(const startup_info* info) {
 const auto argv=reinterpret_cast<const char* const*>(info->argv);
 if(info->argc>1 && equal(argv[1],"fault")) {
  request reserved{1,64,1,1,base,page,page,0,0,0,0};
  if(call(reserved)!=static_cast<i64>(base))return fail("fault_reserve");
  print("VM1_RESERVED_READ\n");
  return *reinterpret_cast<volatile unsigned char*>(base);
 }
 request stats{1,64,0xffff,0,0,0,0,0,0,0,0};
 const i64 before=call(stats); if(before<=0)return fail("stats");
 request large{1,64,1,1,base,4ull<<40,1ull<<40,0,0,0,0};
 if(call(large)!=static_cast<i64>(base) || call(stats)!=before)return fail("sparse_reserve");
 large.address=base+(4ull<<40);
 if(call(large)!=static_cast<i64>(large.address) || call(stats)!=before)return fail("sparse_quota");
 request excess{1,64,1,1,base+(8ull<<40),page,page,0,0,0,0};
 if(call(excess)!=-4)return fail("sparse_quota_limit");
 large.operation=5;large.flags=0;large.alignment=0;
 if(call(large)!=0 || call(stats)!=before)return fail("sparse_unmap");
 large.address=base;
 if(call(large)!=0 || call(stats)!=before)return fail("sparse_unmap_first");
 request r{1,64,1,1,base,4*page,page,0,0,0,0};
 if(call(r)!=static_cast<i64>(base)) return fail("reserve");
 if(syscall(sys_process_fork_prepare)!=process_error_state ||
    syscall(sys_process_exec_prepare)!=process_error_state) return fail("lifecycle_guard");
 if(call(r)!=-7) return fail("collision");
 r.operation=5;r.flags=0;r.address=base+page;r.length=2*page;r.alignment=0;
 if(call(r)!=0) return fail("split");
 r.operation=1;r.flags=1;r.alignment=page;
 if(call(r)!=static_cast<i64>(base+page)) return fail("reuse");
 r.flags=0;r.address=base;r.length=page;
 if(call(r)!=static_cast<i64>(base+4*page)) return fail("hint_fallback");
 r.operation=5;r.flags=0;r.address=base;r.length=8*page;r.alignment=0;
 if(call(r)!=0 || call(r)!=0) return fail("unmap_hole");
 r.operation=1;r.flags=1;r.address=end-page;r.length=2*page;r.alignment=page;
 if(call(r)!=-1) return fail("overflow");
 r.address=base;r.length=page;r.reserved0=1;
 if(call(r)!=-1) return fail("reserved");
 r.reserved0=0;r.alignment=page;
 for(u32 i=0;i<256;++i) { r.address=base+u64(i)*3*page;if(call(r)!=static_cast<i64>(r.address))return fail("fragment_fill"); }
 if(call(stats)!=before)return fail("fragment_physical_pages");
 r.address=base+800*page;if(call(r)!=-4)return fail("fragment_limit");
 r.operation=5;r.flags=0;r.address=base;r.length=256*3*page;r.alignment=0;
 if(call(r)!=0) return fail("clear");
 r.operation=1;r.flags=1;r.address=base;r.length=3*page;r.alignment=page;
 if(call(r)!=static_cast<i64>(base))return fail("split_setup");
 for(u32 i=1;i<256;++i){r.address=base+(u64(i)*3+1)*page;r.length=page;if(call(r)!=static_cast<i64>(r.address))return fail("split_fill");}
 r.operation=5;r.flags=0;r.address=base+page;r.length=page;r.alignment=0;
 if(call(r)!=-4)return fail("split_rollback");
 r.operation=1;r.flags=1;r.address=base+page;r.length=page;r.alignment=page;
 if(call(r)!=-7)return fail("rollback_preserved");
 if(call(stats)!=before)return fail("rollback_physical_pages");
 if(syscall(67,0)!=-2 || syscall(67,1)!=-2 ||
    syscall(67,0x7ffffff0ull)!=-2)return fail("request_pointer");
 print("VM1_GUEST_PASS\n");return 0;
}
