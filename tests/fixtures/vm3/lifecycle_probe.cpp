// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
using namespace xos;
using namespace xos::sdk;
namespace {
struct exec_marker { u64 magic; u32 version, size; };
[[gnu::section(".xos.exec"), gnu::used]] const exec_marker marker{exec_image_abi_magic,3,sizeof(exec_marker)};
struct request { u32 version,size,operation,flags; u64 address,length,alignment; u32 protection,reserved0; u64 reserved1,reserved2; };
constexpr u64 base=0x100000000000ull, page=4096;
i64 vm(request& r) { return syscall(67,reinterpret_cast<u64>(&r)); }
int fail(const char* text) { print("VM3_FAIL ");print(text);print("\n");return 1; }
file::client files;
}
extern "C" int xos_user_main(const startup_info* info) {
 const auto argv=reinterpret_cast<const char* const*>(info->argv);
 if(info->argc>1 && equal(argv[1],"cancel")) {
  request large{1,64,1,1,base,1024*page,page,0,0,0,0};
  if(vm(large)!=static_cast<i64>(base))return fail("cancel_reserve");
  large.operation=2;large.flags=0;large.alignment=0;large.protection=3;
  if(vm(large))return fail("cancel_commit");
  print("VM3_CANCEL_FORK_START\n");
  (void)syscall(sys_process_fork_prepare);
  return fail("cancel_fork_returned");
 }
 request r{1,64,1,1,base,3*page,page,0,0,0,0};
 if(info->argc>1 && equal(argv[1],"after")) {
  if(vm(r)!=static_cast<i64>(base))return fail("exec_vma_not_cleared");
  r.operation=5;r.flags=0;r.alignment=0;
  if(vm(r))return fail("exec_cleanup");
  print("VM3_EXEC_PASS\n");return 0;
 }
 if(vm(r)!=static_cast<i64>(base))return fail("reserve");
 r.operation=2;r.flags=0;r.length=2*page;r.alignment=0;r.protection=3;
 if(vm(r))return fail("commit");
 auto* p=reinterpret_cast<volatile u64*>(base);p[0]=17;p[page/8]=23;
 r.operation=3;r.address=base+page;r.length=page;r.protection=0;
 if(vm(r))return fail("hide");
 const i64 stage=syscall(sys_process_exec_prepare);
 if(stage<=0)return fail("exec_prepare");
 process_entry invalid{};
 if(syscall(sys_process_exec_commit,static_cast<u64>(stage),reinterpret_cast<u64>(&invalid))!=process_error_invalid)
  return fail("exec_commit_failure");
 if(syscall(sys_process_abort,static_cast<u64>(stage)))return fail("exec_abort");
 r.protection=3;if(vm(r) || p[page/8]!=23)return fail("exec_abort_preserve");
 r.protection=0;if(vm(r))return fail("rehide");
 request stats{1,64,0xffff,0,0,0,0,0,0,0,0};
 const i64 before=vm(stats);
 request inject{1,64,0xfffa,0,0,0,0,0,0,0,0};
 bool exhausted=false;
 for(u32 n=0;n<1024;++n) {
  inject.address=n;
  if(vm(inject))return fail("fork_failure_injection");
  const i64 attempt=syscall(sys_process_fork_prepare);
  if(attempt>0) {
   if(syscall(sys_process_abort,static_cast<u64>(attempt)))return fail("fork_failure_abort");
   exhausted=true;
  } else if(attempt!=process_error_resources)return fail("fork_failure_status");
  if(vm(stats)!=before || p[0]!=17)return fail("fork_failure_rollback");
  if(exhausted) { print("VM3_FORK_OOM_SWEEP_PASS\n");break; }
 }
 if(!exhausted)return fail("fork_failure_bound");
 const i64 child=syscall(sys_process_fork_prepare);
 if(child==0) {
  request collision{1,64,1,1,base,3*page,page,0,0,0,0};
  if(vm(collision)!=-7)return fail("fork_vma");
  request show{1,64,3,0,base+page,page,0,3,0,0,0};
  if(vm(show) || p[0]!=17 || p[page/8]!=23)return fail("fork_content");
  p[0]=91;p[page/8]=92;
  print("VM3_CHILD_PASS\n");return 0;
 }
 if(child<0)return fail("fork_prepare");
 if(!files.init())return fail("files_init");
 i64 cloned=static_cast<i64>(file::status::would_block);
 for(u32 i=0;i<128 && cloned==static_cast<i64>(file::status::would_block);++i) {
  cloned=files.clone_session(static_cast<u64>(child));if(cloned==static_cast<i64>(file::status::would_block))yield();
 }
 if(cloned || syscall(sys_process_fork_commit,static_cast<u64>(child)))return fail("fork_commit");
 process_status status{};
 if(wait(static_cast<u64>(child),status) || status.outcome!=process_outcome::exited || status.code)return fail("fork_child");
 r.protection=3;
 if(vm(r) || p[0]!=17 || p[page/8]!=23)return fail("fork_isolation");
 print("VM3_FORK_PASS\n");
 const char* args[]={"vm3","after"};spawn_options options{};options.replace_image=true;
 const i64 replaced=spawn_file_options("/bin/vm3.elf",2,args,options);
 (void)replaced;return fail("exec_replace");
}
