// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include "sha256.hpp"
static xos::file::Client files;
static unsigned char data[1024];
extern "C" xos::i64 real_open(xos::file::Client*,const char*,xos::u32,xos::u32&,xos::u32&,xos::u32&) asm("__real__ZN3xos4file6Client4openEPKcjRjS4_S4_");
extern "C" xos::i64 wrapped_open(xos::file::Client*,const char*,xos::u32,xos::u32&,xos::u32&,xos::u32&) asm("__wrap__ZN3xos4file6Client4openEPKcjRjS4_S4_");
extern "C" xos::i64 wrapped_open(xos::file::Client* c,const char* path,xos::u32 flags,xos::u32& h,xos::u32& size,xos::u32& version){
 const auto result=real_open(c,path,flags,h,size,version);
 if(result==0 && xos::sdk::equal(path,"/bin/fault.elf")){
  sha256 hash;xos::u32 total=0;
  while(total<size){const auto n=c->read(h,data,sizeof(data));if(n<=0){(void)c->close(h);return -7;}hash.update(data,static_cast<xos::usize>(n));total+=static_cast<xos::u32>(n);}
  xos::u8 digest[32];char output[65];hash.finish(digest);hex_digest(digest,output);
  if(c->seek(h,0)!=0){(void)c->close(h);return -7;}
  xos::sdk::print("FB0_LOADER_SHA256=");xos::sdk::print(output);xos::sdk::print("\n");
 }
 return result;
}
static void number(const char* label,xos::i64 n){xos::sdk::print(label);xos::sdk::signed_decimal(n);xos::sdk::print("\n");}
extern "C" int xos_user_main(const xos::startup_info* info){
 if(!files.init())return 1;
 const auto argv=reinterpret_cast<const char* const*>(info->argv);
 if(info->argc>1 && xos::sdk::equal(argv[1],"service_exit")){
  xos::u32 size=0,version=0;const auto result=files.stat("/FB0FAULT",size,version);number("FB0_SERVICE_EXIT_STAT=",result);
  const auto ping=files.ping();number("FB0_SERVICE_EXIT_PING=",ping);return result<0 && ping<0 ? 0 : 13;
 }
 if(info->argc>1 && xos::sdk::equal(argv[1],"loader")){
  const char* args[]={"fault"};const auto child=xos::sdk::spawn_file("/bin/fault.elf",1,args);if(child<0){number("FB0_SPAWN_ERROR=",child);return 11;}
  const auto invalid=xos::sdk::syscall(xos::sys_process_wait,static_cast<xos::u64>(child),1,1);number("FB0_INVALID_WAIT=",invalid);
  xos::process_status status{};const auto waited=xos::sdk::wait(static_cast<xos::u64>(child),status);
  number("FB0_WAIT_RESULT=",waited);number("FB0_WAIT_VECTOR=",static_cast<xos::i64>(status.vector));number("FB0_WAIT_ADDRESS=",static_cast<xos::i64>(status.address));number("FB0_WAIT_RIP=",static_cast<xos::i64>(status.instruction));
  const auto duplicate=xos::sdk::wait(static_cast<xos::u64>(child),status);number("FB0_WAIT_AGAIN=",duplicate);
  if(invalid>=0||waited!=0||status.outcome!=xos::process_outcome::faulted||status.vector!=14||status.address!=0x100000||status.instruction==0||duplicate>=0)return 12;
  xos::sdk::print("FB0_LOADER_WAIT_OK\n");return 0;
 }
 if(info->argc>1 && xos::sdk::equal(argv[1],"degraded")){
  xos::sdk::print("FB0_DEATH_READY\n");const auto deadline=xos::sdk::ticks()+3000;
  while(xos::sdk::ticks()<deadline)xos::sdk::yield();
  const auto r=files.ping();number("FB0_DEATH_PING=",r);return r<0?0:2;
 }
 if(info->argc>1 && xos::sdk::equal(argv[1],"hash")){
  xos::u32 handle=0,size=0,version=0;if(files.open("/bin/probe.elf",xos::file::read_only,handle,size,version)!=0)return 8;
  sha256 hash;xos::u32 total=0;while(total<size){const auto n=files.read(handle,data,sizeof(data));if(n<=0)return 9;hash.update(data,static_cast<xos::usize>(n));total+=static_cast<xos::u32>(n);}
  xos::u8 digest[32];char output[65];hash.finish(digest);hex_digest(digest,output);
  if(files.close(handle)!=0)return 10;
  xos::sdk::print("FB0_ELF_SHA256=");xos::sdk::print(output);xos::sdk::print("\n");return 0;
 }
 xos::u32 h=0,size=0,v=0;
 auto r=files.open("/PROBE.DAT",xos::file::read_only,h,size,v);if(r!=0||size>sizeof(data))return 3;
 xos::u32 used=0;while(used<size){r=files.read(h,data+used,size-used);if(r<=0)return 4;used+=static_cast<xos::u32>(r);}
 static constexpr char hex[]="0123456789abcdef";xos::sdk::print("FB0_BYTES=");
 for(xos::u32 i=0;i<used;++i){char b[3]={hex[data[i]>>4],hex[data[i]&15],0};xos::sdk::print(b);}xos::sdk::print("\n");
 number("FB0_REPLACE=",files.replace("/PROBE.DAT","bad",3));
 if(files.seek(h,0)!=0)return 5;
 unsigned char again[64];
 for(xos::u32 pos=0;pos<used;){const auto n=files.read(h,again,64);if(n<=0)return 6;for(xos::i64 i=0;i<n;++i){if(again[i]!=data[pos+static_cast<xos::u32>(i)])return 6;}pos+=static_cast<xos::u32>(n);}
 if(files.close(h)!=0)return 7;
 xos::sdk::print("FB0_PINNED_OK\n");return 0;
}
