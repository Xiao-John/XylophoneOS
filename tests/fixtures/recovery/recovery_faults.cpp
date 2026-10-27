// SPDX-License-Identifier: Apache-2.0
// Exercise the production service recovery against real FatFs with API-boundary faults.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "ff.h"
#include "diskio.h"
FRESULT injected_stat(const TCHAR*,FILINFO*);
FRESULT injected_unlink(const TCHAR*);
FRESULT injected_rename(const TCHAR*,const TCHAR*);
FRESULT injected_read(FIL*,void*,UINT,UINT*);
FRESULT injected_close(FIL*);
DRESULT injected_control(BYTE,BYTE,void*);
#define f_stat injected_stat
#define f_unlink injected_unlink
#define f_rename injected_rename
#define f_read injected_read
#define f_close injected_close
#define disk_ioctl injected_control
#include "../../../src/user/services/files.cpp"
#undef f_stat
#undef f_unlink
#undef f_rename
#undef f_read
#undef f_close
#undef disk_ioctl

namespace xos::sdk { i64 syscall(u64,u64,u64,u64) { return 0; } }
namespace {
std::vector<unsigned char> original, media;
std::string fault_op,fault_path;
int fault_nth=1, seen=0, checks=0;
bool hit(const char* operation,const char* path="") {
    return fault_op==operation&&(fault_path.empty()||fault_path==path)&&++seen==fault_nth;
}
void require(bool value,const char* why) { if(!value) {std::fprintf(stderr,"FAIL %s [%s %s nth=%d]\n",why,fault_op.c_str(),fault_path.c_str(),fault_nth);std::exit(1);} }
void put(const char* path,const char* data,UINT length) {
    FIL f{};UINT count=0;
    require(f_open(&f,path,FA_CREATE_ALWAYS|FA_WRITE)==FR_OK,"fixture open");
    require(f_write(&f,data,length,&count)==FR_OK&&count==length,"fixture write");
    require(f_close(&f)==FR_OK,"fixture close");
}
std::string get(const char* path) {
    FIL f{};if(f_open(&f,path,FA_READ)!=FR_OK)return "<absent>";
    char bytes[512]{};UINT got=0;require(f_read(&f,bytes,sizeof(bytes),&got)==FR_OK,"inspect read");
    require(f_close(&f)==FR_OK,"inspect close");return std::string(bytes,got);
}
void setup(bool journal=true,bool target=true,bool backup=true) {
    fault_op.clear();fault_path.clear();seen=0;fault_nth=1;
    f_mount(nullptr,"",0);media=original;fs=FATFS{};recovery_failed=false;mounted=true;
    require(f_mount(&fs,"",1)==FR_OK,"fixture mount");
    put(temp_name,"new-stage",9);
    if(target)put("target.txt","committed",9);
    if(backup)put(backup_name,"old",3);
    if(journal)put(journal_name,"target.txt",11);
}
void assert_gate(bool failed) {
    require(recovery_failed==failed,"recovery gate");
    request in{};in.magic=request_magic;in.version=abi_version;in.operation=static_cast<u16>(op::stat);
    in.name_length=10;std::memcpy(in.name,"target.txt",10);
    response out{};client_session client{};client.pid=7;
    handle(in,out,client,0);
    require((out.status_code==static_cast<i32>(status::io))==failed,"normal request gate");
}
void failure(const char* operation,const char* path,int nth=1,bool target=true,bool journal=true) {
    setup(journal,target,true);fault_op=operation;fault_path=path;fault_nth=nth;
    recover();require(seen>=nth,"fault reached");assert_gate(true);
    fault_op.clear();
    if(journal)require(get(journal_name)==std::string("target.txt",11),"journal retained/restored");
    const auto value=get("target.txt");
    require(value=="committed"||value=="old"||get(backup_name)=="old","recoverable data retained");
    if(std::string(operation)=="stat"||std::string(operation)=="read"||std::string(operation)=="close") {
        require(get(temp_name)=="new-stage","preflight preserves stage");
        require(get(backup_name)=="old","preflight preserves backup");
    }
    ++checks;
}
}
extern "C" DSTATUS disk_initialize(BYTE p) {return p?STA_NOINIT:0;}
extern "C" DSTATUS disk_status(BYTE p) {return disk_initialize(p);}
extern "C" DRESULT disk_read(BYTE p,BYTE* b,LBA_t s,UINT n) {
    if(p||s>=media.size()/512||n>media.size()/512-s)return RES_PARERR;
    std::memcpy(b,media.data()+s*512,size_t(n)*512);return RES_OK;
}
extern "C" DRESULT disk_write(BYTE p,const BYTE* b,LBA_t s,UINT n) {
    if(p||s>=media.size()/512||n>media.size()/512-s)return RES_PARERR;
    std::memcpy(media.data()+s*512,b,size_t(n)*512);return RES_OK;
}
extern "C" DRESULT disk_ioctl(BYTE p,BYTE op,void* b) {
    if(p)return RES_PARERR;
    if(op==CTRL_SYNC)return RES_OK;
    if(op==GET_SECTOR_COUNT){*static_cast<LBA_t*>(b)=media.size()/512;return RES_OK;}
    if(op==GET_SECTOR_SIZE){*static_cast<WORD*>(b)=512;return RES_OK;}
    if(op==GET_BLOCK_SIZE){*static_cast<DWORD*>(b)=1;return RES_OK;}
    return RES_PARERR;
}
FRESULT injected_stat(const TCHAR* p,FILINFO* out){return hit("stat",p)?FR_DISK_ERR:f_stat(p,out);}
FRESULT injected_unlink(const TCHAR* p){return hit("unlink",p)?FR_DISK_ERR:f_unlink(p);}
FRESULT injected_rename(const TCHAR* a,const TCHAR* b){return hit("rename",a)?FR_DISK_ERR:f_rename(a,b);}
FRESULT injected_read(FIL* f,void* b,UINT n,UINT* got){return hit("read")?FR_DISK_ERR:f_read(f,b,n,got);}
FRESULT injected_close(FIL* f){const auto r=f_close(f);return hit("close")?FR_DISK_ERR:r;}
DRESULT injected_control(BYTE p,BYTE op,void* b){return hit("sync")?RES_ERROR:disk_ioctl(p,op,b);}
int main(int argc,char** argv) {
    require(argc==2,"image argument");FILE* image=std::fopen(argv[1],"rb");require(image,"fixture image");
    std::fseek(image,0,SEEK_END);original.resize(size_t(std::ftell(image)));std::rewind(image);
    require(std::fread(original.data(),1,original.size(),image)==original.size(),"fixture image read");std::fclose(image);
    for(const char* path:{journal_name,"target.txt",backup_name,temp_name})failure("stat",path);
    failure("read","");failure("close","");
    for(const char* path:{temp_name,backup_name,journal_name})failure("unlink",path);
    failure("rename",backup_name,1,false);
    for(int nth=1;nth<=3;++nth)failure("sync","",nth);
    failure("stat",journal_name,1,true,false);failure("stat",temp_name,1,true,false);failure("unlink",temp_name,1,true,false);failure("sync","",1,true,false);
    setup();recover();assert_gate(false);require(get("target.txt")=="committed","commit data");require(get(journal_name)=="<absent>","journal cleaned");++checks;
    setup(true,false,true);recover();assert_gate(false);require(get("target.txt")=="old","backup restored");++checks;
    setup(false);recover();assert_gate(false);require(get(temp_name)=="<absent>","orphan temp cleaned");++checks;
    // FR_NO_PATH is an explicit absence result, not a generic I/O error.
    setup(false);FILINFO info{};require(remove_if_present("missing/file")==true,"absent parent accepted");++checks;
    std::printf("RECOVERY_CASES_PASSED=%d\n",checks);
}
