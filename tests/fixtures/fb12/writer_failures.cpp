// SPDX-License-Identifier: Apache-2.0
// Host-only failure injection of the actual user-mode fault bundle writer.
#include <cstring>
#include <cstdio>
#include "../../../src/user/programs/fault_bundle.hpp"
using namespace xos;
static int scenario, writes, closes, syncs, renames, saved;
namespace xos::sdk {
i64 syscall(u64 number,u64 first,u64,u64){
 if(number==sys_random_bytes){if(scenario==6)return -5;auto* p=reinterpret_cast<u8*>(first);for(u32 i=0;i<16;++i)p[i]=static_cast<u8>(i);return 0;}return -1;
}
void print(const char* text,u32){if(std::strstr(text,"[fault-bundle] saved"))++saved;}
}
namespace xos::file {
bool Client::init(){return true;}
i64 Client::mkdir(const char* path){return std::strcmp(path,"/FAULTS")==0?static_cast<i64>(status::exists):0;}
i64 Client::list(const char*,entry*,u32,u32& count,u32& cursor){count=0;cursor=0;return 0;}
i64 Client::open(const char*,u32,u32& h,u32& size,u32& version){h=static_cast<u32>(++writes);size=version=0;return 0;}
i64 Client::write(u32,const void*,u32 length){if(scenario==1)return 0;if(scenario==7&&length>1)return static_cast<i64>(length/2);return static_cast<i64>(length);}
i64 Client::close(u32){++closes;return scenario==2?-7:0;}
i64 Client::sync(){++syncs;if(scenario==3&&syncs==1)return -8;if(scenario==5&&syncs==3)return -7;return 0;}
i64 Client::rename(const char*,const char*){++renames;return scenario==4?-7:0;}
}
int main(){
 xos::process_status st{1,xos::process_outcome::faulted,7,0,14,0x100000,0x400000bf};fault_bundle::receipt image{};image.size=123;
 for(scenario=0;scenario<=7;++scenario){writes=closes=syncs=renames=saved=0;const bool ok=fault_bundle::save(st,image);
  const bool expected=scenario==0||scenario==7;
  if(expected!=ok||saved!=(expected?1:0))return 10+scenario;
  if(scenario>=1&&scenario<=3&&renames!=0)return 20+scenario;
  if(scenario==4&&renames!=1)return 24;
  if(scenario==5&&(renames!=1||syncs!=3))return 25;
 }
 std::puts("PASS writer success and positive short writes; zero write, close, sync, rename, final sync and random failures do not report success");return 0;
}
