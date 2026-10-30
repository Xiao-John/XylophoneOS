// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <xos/thread_abi.hpp>
#include <xos/fault_sha256.hpp>
#include <xos/execution.hpp>
namespace fault_bundle {
using namespace xos;
using receipt = execution::image_receipt;
static file::Client client;
static file::entry entry_buffer[4];
struct buffer {
 char data[2048]{}; u32 used=0; bool valid=true;
 void text(const char* s){while(*s){if(used+1>=sizeof(data)){valid=false;return;}data[used++]=*s++;}data[used]=0;}
 void unsigned_decimal(u64 n){char v[21];u32 k=0;do{v[k++]=static_cast<char>('0'+n%10);n/=10;}while(n);while(k){char x[2]={v[--k],0};text(x);}}
 void signed_decimal(i64 n){if(n<0){text("-");unsigned_decimal(u64{0}-static_cast<u64>(n));}else unsigned_decimal(static_cast<u64>(n));}
 void hex64(u64 n){static constexpr char h[]="0123456789abcdef";char v[17];v[16]=0;for(int i=15;i>=0;--i){v[i]=h[n&15];n>>=4;}text(v);}
};
static bool write_file(const char* path,const buffer& value){
 if(!value.valid)return false;
 u32 h=0,n=0,v=0;
 if(client.open(path,file::write_only|file::open_create|file::open_exclusive,h,n,v)!=0)return false;
 u32 off=0;bool ok=true;while(off<value.used){u32 amount=value.used-off;if(amount>file::request_data_size)amount=file::request_data_size;
  const auto wrote=client.write(h,value.data+off,amount);if(wrote<=0||static_cast<u64>(wrote)>amount){ok=false;break;}off+=static_cast<u32>(wrote);}
 if(client.close(h)!=0)ok=false;
 return ok;
}
static void append_path(char* out,const char* a,const char* b){u32 i=0;while(*a)out[i++]=*a++;out[i++]='/';while(*b)out[i++]=*b++;out[i]=0;}
static bool quota(){
 u32 cursor=0,total=0,dirs=0;
 do {u32 count=0;const u32 before=cursor;if(client.list("/FAULTS",entry_buffer,4,count,cursor)!=0)return false;
  for(u32 i=0;i<count;++i){if(!entry_buffer[i].directory||++dirs>=16)return false;char dir[300];append_path(dir,"/FAULTS",entry_buffer[i].name);
   u32 sub=0;do{file::entry children[2]{};u32 got=0;const u32 previous=sub;if(client.list(dir,children,2,got,sub)!=0)return false;
    for(u32 j=0;j<got;++j){if(children[j].directory||children[j].size>131072||total>2097152-children[j].size)return false;total+=children[j].size;}
    if(sub&&sub==previous)return false;
   }while(sub);
  }if(cursor&&cursor==before)return false;
 }while(cursor);return total<=2097152-131072;
}
static void hash_text(const buffer& b,char out[65]){sha256 hash;hash.update(b.data,b.used);u8 digest[32];hash.finish(digest);hex_digest(digest,out);}
static bool save(const process_status& st,const receipt& image){
 if(st.outcome!=process_outcome::faulted)return true;
 if(st.version!=1||st.vector>255)return false;
 if(!client.init())return false;
 const auto mk=client.mkdir("/FAULTS");if(mk!=0&&mk!=static_cast<i64>(file::status::exists))return false;
 if(!quota())return false;
 u8 random[16];char id[33];static constexpr char hex[]="0123456789abcdef";
 if(sdk::syscall(sys_random_bytes,reinterpret_cast<u64>(random),sizeof(random))!=0)return false;
 for(u32 i=0;i<16;++i){id[2*i]=hex[random[i]>>4];id[2*i+1]=hex[random[i]&15];}id[32]=0;
 char dir[64];append_path(dir,"/FAULTS",id);if(client.mkdir(dir)!=0)return false;
 char image_hash[65];hex_digest(image.digest,image_hash);
 buffer report;report.text("{\"version\":1,\"run_id\":\"");report.text(id);report.text("\",\"status_version\":1,\"outcome\":\"faulted\",\"pid\":\"");report.hex64(st.pid);report.text("\",\"code\":\"");report.signed_decimal(st.code);report.text("\",\"vector\":");report.unsigned_decimal(st.vector);report.text(",\"address\":");if(st.vector==14){report.text("\"");report.hex64(st.address);report.text("\"");}else report.text("null");report.text(",\"instruction\":\"");report.hex64(st.instruction);report.text("\"}");
 buffer img;img.text("{\"version\":1,\"run_id\":\"");img.text(id);img.text("\",\"source\":\"file\",\"size\":");img.unsigned_decimal(image.size);img.text(",\"sha256\":\"");img.text(image_hash);img.text("\",\"elf_type\":\"ET_EXEC\",\"sdk_profile\":null,\"build_id\":null}");
 buffer context;context.text("{\"version\":1,\"run_id\":\"");context.text(id);context.text("\",\"collector_version\":\"fb1-v1\",\"system_build_id\":null,\"monotonic_ns\":null,\"utc_ns\":null}");
 char h1[65],h2[65],h3[65];hash_text(report,h1);hash_text(img,h2);hash_text(context,h3);
 buffer manifest;manifest.text("{\"version\":1,\"run_id\":\"");manifest.text(id);manifest.text("\",\"state\":\"complete\",\"files\":{");
 const char* names[]={"report.json","image.json","context.json"};const buffer* vals[]={&report,&img,&context};const char* hashes[]={h1,h2,h3};
 for(u32 i=0;i<3;++i){if(i)manifest.text(",");manifest.text("\"");manifest.text(names[i]);manifest.text("\":{\"size\":");manifest.unsigned_decimal(vals[i]->used);manifest.text(",\"sha256\":\"");manifest.text(hashes[i]);manifest.text("\"}");}manifest.text("}}");
 char path[96];for(u32 i=0;i<3;++i){append_path(path,dir,names[i]);if(!write_file(path,*vals[i]))return false;}
 if(client.sync()!=0)return false;
 append_path(path,dir,"manifest.tmp");if(!write_file(path,manifest)||client.sync()!=0)return false;
 char final_path[96];append_path(final_path,dir,"manifest.json");
 if(client.rename(path,final_path)!=0||client.sync()!=0)return false;
 sdk::print("[fault-bundle] saved ");sdk::print(dir);sdk::print("\n");return true;
}
}
