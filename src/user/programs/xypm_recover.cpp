// SPDX-License-Identifier: Apache-2.0
// Immutable boot-module recovery worker for a P2 transaction journal.
#include <xos/sdk.hpp>
#include <xos/file_client.hpp>
#include "xypm_journal.hpp"
#include <string.h>

using namespace xos;
namespace {
using namespace xypm_journal;
file::Client files;
#ifdef XYP_RECOVERY_TEST
u32 recovery_fault_after,recovery_checkpoint_count;
void recovery_checkpoint(){++recovery_checkpoint_count;if(recovery_fault_after==recovery_checkpoint_count){sdk::print("xypm-recover-test: injected=");sdk::decimal(recovery_checkpoint_count);sdk::print("\n");(void)files.sync();sdk::exit(70);}}
#else
void recovery_checkpoint(){}
#endif
header journal{};
record records[max_records]{};
directory directories[max_directories]{};
u8 buffer[2048];
constexpr i64 missing = static_cast<i64>(file::status::not_found);

enum class state { absent, present, error };
int failure(const char* message) { sdk::print("xypm-recover: "); sdk::print(message); sdk::print("\n"); return 1; }
state stat_path(const char* path, u32& size, u32& attributes) {
    i64 result=files.stat_info(path,size,attributes);
    return result==0?state::present:result==missing?state::absent:state::error;
}
bool read_exact(u32 handle,void* target,u32 length) {
    auto* out=static_cast<u8*>(target);u32 done=0;
    while(done<length){u32 wanted=length-done;if(wanted>sizeof(buffer))wanted=sizeof(buffer);i64 n=files.read(handle,out+done,wanted);if(n<=0)return false;done+=static_cast<u32>(n);}
    return true;
}
bool fixed_string(const char* path,size_t capacity) {
    size_t end=0;while(end<capacity&&path[end])++end;
    if(end==0||end==capacity)return false;
    for(size_t i=end;i<capacity;++i)if(path[i])return false;
    return true;
}
bool permitted_path(const char* path,bool is_directory) {
    const size_t n=strlen(path);if(n<4||n>=file::max_name||path[0]!='/'||path[n-1]=='/')return false;
    if(!is_directory&&(sdk::equal(path,"/var/lib/xypm/db.json")||sdk::equal(path,"/var/lib/xypm/index.tsv")))return true;
    if(memcmp(path,"/usr",4)!=0||(n>4&&path[4]!='/'))return false;
    if(n==4)return is_directory;
    const char* root=path+5;
    size_t root_len=0;while(root[root_len]&&root[root_len]!='/')++root_len;
    if(!((root_len==3&&memcmp(root,"bin",3)==0)||(root_len==3&&memcmp(root,"lib",3)==0)||(root_len==5&&memcmp(root,"share",5)==0)))return false;
    if(!is_directory&&root[root_len]==0)return false;
    size_t component=0;const char* start=path+1;
    for(size_t i=1;i<=n;++i){char c=path[i];if(c=='/'||c==0){if(component==0||component>100||start[component-1]=='.'||(component==1&&start[0]=='.')||(component==2&&start[0]=='.'&&start[1]=='.'))return false;
        if(component>=7&&(start[0]=='X'||start[0]=='x')&&(start[1]=='O'||start[1]=='o')&&(start[2]=='S'||start[2]=='s')&&start[component-4]=='.'&&(start[component-3]=='T'||start[component-3]=='t')&&(start[component-2]=='M'||start[component-2]=='m')&&(start[component-1]=='P'||start[component-1]=='p'))return false;
        component=0;start=path+i+1;continue;}
        if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='.'||c=='+'||c=='-'))return false;
        ++component;}
    return true;
}
int fold_compare(const char* a,const char* b) {
    while(*a&&*b){char x=*a++,y=*b++;if(x>='A'&&x<='Z')x+=32;if(y>='A'&&y<='Z')y+=32;if(x!=y)return static_cast<unsigned char>(x)<static_cast<unsigned char>(y)?-1:1;}
    return *a?1:*b?-1:0;
}
bool zero_hash(const u8* hash){for(unsigned i=0;i<32;++i)if(hash[i])return false;return true;}
bool load_journal() {
    u32 size=0,attributes=0;if(stat_path(marker,size,attributes)!=state::present||(attributes&file::stat_is_directory)||size<sizeof(header))return false;
    u32 handle=0,opened=0,version_value=0;if(files.open(marker,file::read_only,handle,opened,version_value)!=0||opened!=size)return false;
    bool ok=read_exact(handle,&journal,sizeof(journal));
    if(ok)ok=memcmp(journal.magic,magic,8)==0&&journal.version==version&&journal.reserved==0&&journal.record_count>0&&journal.record_count<=max_records&&journal.directory_count<=max_directories;
    u64 expected=sizeof(header)+u64(journal.record_count)*sizeof(record)+u64(journal.directory_count)*sizeof(directory);
    if(ok)ok=expected==size;
    sha256 hash;if(ok)hash.update(&journal,24);
    for(u32 i=0;ok&&i<journal.record_count;++i){ok=read_exact(handle,&records[i],sizeof(record));if(ok)hash.update(&records[i],sizeof(record));}
    for(u32 i=0;ok&&i<journal.directory_count;++i){ok=read_exact(handle,&directories[i],sizeof(directory));if(ok)hash.update(&directories[i],sizeof(directory));}
    u8 digest[32];if(ok){hash.finish(digest);ok=memcmp(digest,journal.digest,32)==0;}
    if(files.close(handle)!=0)ok=false;
    if(!ok)return false;
    for(u32 i=0;i<journal.record_count;++i){const record& r=records[i];if(!fixed_string(r.path,sizeof(r.path))||!permitted_path(r.path,false)||(r.flags&~3u)||!r.flags||r.old_size>(64u<<20)||r.new_size>(64u<<20))return false;
        if(!(r.flags&old_present)&&(r.old_size||!zero_hash(r.old_hash)))return false;
        if(!(r.flags&new_present)&&(r.new_size||!zero_hash(r.new_hash)))return false;
        if(i&&fold_compare(records[i-1].path,r.path)>=0)return false;
    }
    for(u32 i=0;i<journal.directory_count;++i){if(!fixed_string(directories[i].path,sizeof(directories[i].path))||!permitted_path(directories[i].path,true)||!directories[i].flags||(directories[i].flags&~3u))return false;if(i&&fold_compare(directories[i-1].path,directories[i].path)>=0)return false;}
    return true;
}
void numbered_path(char* out,const char* parent,u32 index){size_t n=strlen(parent);memcpy(out,parent,n);out[n++]='/';for(int i=7;i>=0;--i){out[n+i]=char('0'+index%10);index/=10;}out[n+8]=0;}
state file_hash(const char* path,u32& size,u8 digest[32]) {
    u32 attrs=0;state s=stat_path(path,size,attrs);if(s!=state::present)return s;if(attrs&file::stat_is_directory)return state::error;
    u32 handle=0,opened=0,v=0;if(files.open(path,file::read_only,handle,opened,v)!=0||opened!=size)return state::error;
    sha256 hash;u32 remaining=size;bool ok=true;while(remaining){u32 amount=remaining>sizeof(buffer)?sizeof(buffer):remaining;i64 n=files.read(handle,buffer,amount);if(n<=0){ok=false;break;}hash.update(buffer,static_cast<u32>(n));remaining-=static_cast<u32>(n);}
    if(files.close(handle)!=0)ok=false;
    if(!ok)return state::error;
    hash.finish(digest);return state::present;
}
bool matches(state s,u32 size,const u8 digest[32],u32 expected_size,const u8 expected_hash[32]){return s==state::present&&size==expected_size&&memcmp(digest,expected_hash,32)==0;}
bool remove_if_exists(const char* path){u32 size=0,attrs=0;state s=stat_path(path,size,attrs);if(s==state::absent)return true;if(s!=state::present||files.remove(path)!=0)return false;recovery_checkpoint();return true;}
bool remove_if_empty_directory(const char* path){u32 size=0,attrs=0;state s=stat_path(path,size,attrs);if(s==state::absent)return true;if(s!=state::present||!(attrs&file::stat_is_directory))return false;file::entry entries[8]{};u32 count=0,cursor=0;if(files.list(path,entries,8,count,cursor)!=0)return false;if(count||cursor)return true;if(files.remove(path)!=0)return false;recovery_checkpoint();return true;}
bool read_stamp(const char* path,const char expected[8],bool& present){
    u32 size=0,attrs=0;state s=stat_path(path,size,attrs);if(s==state::absent){present=false;return true;}
    if(s!=state::present||(attrs&file::stat_is_directory)||size!=8)return false;
    u32 handle=0,opened=0,v=0;char actual[8];if(files.open(path,file::read_only,handle,opened,v)!=0)return false;
    bool ok=opened==8&&read_exact(handle,actual,8)&&memcmp(actual,expected,8)==0;if(files.close(handle)!=0)ok=false;
    present=ok;return ok;
}
bool pending_old[max_records]{},pending_new[max_records]{};
bool scan_pending(const char* path,bool* found){
    u32 size=0,attrs=0;state s=stat_path(path,size,attrs);if(s==state::absent)return true;
    if(s!=state::present||!(attrs&file::stat_is_directory))return false;
    u32 cursor=0;do{file::entry entries[16]{};u32 count=0;if(files.list(path,entries,16,count,cursor)!=0)return false;
        for(u32 i=0;i<count;++i){const char* name=entries[i].name;if(entries[i].directory||strlen(name)!=8)return false;
            u32 number=0;for(unsigned j=0;j<8;++j){if(name[j]<'0'||name[j]>'9')return false;number=number*10+u32(name[j]-'0');}
            if(number>=max_records||found[number])return false;
            found[number]=true;}
    }while(cursor!=0);return true;
}
bool clean_unpublished_preparation(){
    u32 size=0,attrs=0;state data=stat_path(data_dir,size,attrs);if(data!=state::present||!(attrs&file::stat_is_directory))return false;
    bool prep=false,started=false;if(!read_stamp(preparing,prepare_magic,prep)||!read_stamp(applying,applying_magic,started)||started)return false;
    // Validate the entire namespace before removing anything. A missing prepare
    // stamp is only safe when the directory is already completely empty.
    bool saw_entry=false;u32 cursor=0;do{file::entry entries[16]{};u32 count=0;if(files.list(data_dir,entries,16,count,cursor)!=0)return false;
        for(u32 i=0;i<count;++i){const char* name=entries[i].name;saw_entry=true;
            bool allowed=(sdk::equal(name,"old")||sdk::equal(name,"new"))?entries[i].directory:
                         (sdk::equal(name,"prepare")||sdk::equal(name,"journal.tmp")||sdk::equal(name,"reserve")||sdk::equal(name,"reserve2"))&&!entries[i].directory;
            if(!allowed)return false;}
    }while(cursor!=0);
    if(!prep&&saw_entry)return false;
    if(!scan_pending(old_dir,pending_old)||!scan_pending(new_dir,pending_new))return false;
    for(u32 i=0;i<max_records;++i){char path[80];if(pending_old[i]){numbered_path(path,old_dir,i);if(!remove_if_exists(path))return false;}
        if(pending_new[i]){numbered_path(path,new_dir,i);if(!remove_if_exists(path))return false;}}
    return remove_if_exists(old_dir)&&remove_if_exists(new_dir)&&remove_if_exists(journal_temp)&&remove_if_exists(reserve)&&remove_if_exists(reserve2)&&
           remove_if_exists(preparing)&&remove_if_exists(data_dir)&&files.sync()==0;
}
bool read_commit(const char* path,bool& present,commit_record& commit){u32 size=0,attrs=0;state s=stat_path(path,size,attrs);if(s==state::absent){present=false;return true;}if(s!=state::present||(attrs&file::stat_is_directory)||size!=sizeof(commit_record))return false;u32 h=0,opened=0,v=0;if(files.open(path,file::read_only,h,opened,v)!=0)return false;bool ok=opened==sizeof(commit)&&read_exact(h,&commit,sizeof(commit));if(files.close(h)!=0)ok=false;u8 digest[32];sha256 hash;if(ok){hash.update(&commit,40);hash.finish(digest);ok=memcmp(digest,commit.self_hash,32)==0;}present=ok&&memcmp(commit.magic,commit_magic,8)==0;return present;}
bool commit_status(bool& is_committed){bool inner=false,outer=false;commit_record one{},two{};if(!read_commit(committed,inner,one)||!read_commit(commit_final,outer,two)|| (inner&&outer))return false;is_committed=inner||outer;return !is_committed||memcmp((inner?one:two).journal_hash,journal.digest,32)==0;}
bool preflight(bool committed_state){
    for(u32 i=0;i<journal.record_count;++i){const record& r=records[i];u32 target_size=0,backup_size=0,stage_size=0;u8 target_hash[32]{},backup_hash[32]{},stage_hash[32]{};char old_path[80],new_path[80];numbered_path(old_path,old_dir,i);numbered_path(new_path,new_dir,i);
        state target=file_hash(r.path,target_size,target_hash),backup=file_hash(old_path,backup_size,backup_hash),stage=file_hash(new_path,stage_size,stage_hash);
        if(target==state::error||backup==state::error||stage==state::error)return false;
        bool old_ok=(r.flags&old_present)&&matches(target,target_size,target_hash,r.old_size,r.old_hash);
        bool new_ok=(r.flags&new_present)&&matches(target,target_size,target_hash,r.new_size,r.new_hash);
        if(backup==state::present&&(!(r.flags&old_present)||!matches(backup,backup_size,backup_hash,r.old_size,r.old_hash)))return false;
        if(stage==state::present&&(!(r.flags&new_present)||!matches(stage,stage_size,stage_hash,r.new_size,r.new_hash)))return false;
        if(committed_state){if((r.flags&new_present)?!new_ok:target!=state::absent)return false;}
        else {if(target!=state::absent&&!old_ok&&!new_ok)return false;if((r.flags&old_present)&&!old_ok&&backup!=state::present)return false;}
    }
    return true;
}
bool rollback(){
    for(u32 i=0;i<journal.record_count;++i){const record& r=records[i];u32 size=0;u8 digest[32]{};state target=file_hash(r.path,size,digest);bool old_ok=(r.flags&old_present)&&matches(target,size,digest,r.old_size,r.old_hash);if(old_ok)continue;
        if(target==state::present){if(files.remove(r.path)!=0)return false;recovery_checkpoint();}
        if(r.flags&old_present){char old_path[80];numbered_path(old_path,old_dir,i);if(files.rename(old_path,r.path)!=0)return false;recovery_checkpoint();}
        if(files.sync()!=0)return false;
    }
    return true;
}
bool cleanup(bool committed_state){
    for(u32 i=0;i<journal.record_count;++i){char path[80];numbered_path(path,old_dir,i);if(!remove_if_exists(path))return false;numbered_path(path,new_dir,i);if(!remove_if_exists(path))return false;}
    for(u32 i=journal.directory_count;i>0;--i){const directory& dir=directories[i-1];u32 mask=committed_state?remove_after_commit:remove_on_rollback;if((dir.flags&mask)&&!remove_if_empty_directory(dir.path))return false;}
    if(!remove_if_exists(commit_temp)||!remove_if_exists(applying)||!remove_if_exists(preparing)||!remove_if_exists(journal_temp)||!remove_if_exists(reserve)||!remove_if_exists(reserve2)||!remove_if_exists(old_dir)||!remove_if_exists(new_dir)||files.sync()!=0)return false;
    if(committed_state){u32 size=0,attrs=0;state inner=stat_path(committed,size,attrs);if(inner==state::present){if(files.rename(committed,commit_final)!=0||files.sync()!=0)return false;recovery_checkpoint();}else if(inner!=state::absent)return false;}
    if(!remove_if_exists(data_dir)||files.sync()!=0)return false;
    if(files.remove(marker)!=0)return false;
    recovery_checkpoint();
    if(files.sync()!=0){ // Best effort: re-establish the marker; never report success.
        if(committed_state)return false; // commit_final remains as a boot gate.
        u32 handle=0,size=0,v=0;if(files.open(marker,file::write_only|file::open_create|file::open_exclusive,handle,size,v)==0){
            auto write_all=[&](const void* source,u32 length){const auto* p=static_cast<const u8*>(source);u32 done=0;while(done<length){u32 n=length-done;if(n>sizeof(buffer))n=sizeof(buffer);i64 written=files.write(handle,p+done,n);if(written<=0)return false;done+=static_cast<u32>(written);}return true;};
            bool ok=write_all(&journal,sizeof(journal));for(u32 i=0;ok&&i<journal.record_count;++i)ok=write_all(&records[i],sizeof(record));for(u32 i=0;ok&&i<journal.directory_count;++i)ok=write_all(&directories[i],sizeof(directory));(void)ok;(void)files.close(handle);(void)files.sync();}
        return false;
    }
    if(committed_state){if(files.remove(commit_final)!=0)return false;recovery_checkpoint();if(files.sync()!=0){commit_record commit{};memcpy(commit.magic,commit_magic,8);memcpy(commit.journal_hash,journal.digest,32);sha256 hash;hash.update(&commit,40);hash.finish(commit.self_hash);u32 handle=0,size=0,v=0;if(files.open(commit_final,file::write_only|file::open_create|file::open_exclusive,handle,size,v)==0){(void)files.write(handle,&commit,sizeof(commit));(void)files.close(handle);(void)files.sync();}return false;}}
    return true;
}
}
#ifdef XYP_RECOVERY_LIBRARY
extern "C" xos::i64 xypm_acquire_maintenance();
extern "C" int xypm_recover_run() {
    if(!files.init()||xypm_acquire_maintenance()!=0)return failure("maintenance lease unavailable");
#else
extern "C" int xos_user_main(const xos::startup_info* startup) {
#ifdef XYP_RECOVERY_TEST
    if(startup->argc>1){const char* const* argv=reinterpret_cast<const char* const*>(startup->argv);for(const char* p=argv[1];*p;++p){if(*p<'0'||*p>'9'||recovery_fault_after>100000)return 2;recovery_fault_after=recovery_fault_after*10+u32(*p-'0');}}
#else
    (void)startup;
#endif
    if(!files.init()||files.maintenance_acquire()!=0)return failure("maintenance lease unavailable");
#endif
    u32 marker_size=0,marker_attributes=0;state marker_state=stat_path(marker,marker_size,marker_attributes);
    if(marker_state==state::absent){u32 size=0,attrs=0;state data=stat_path(data_dir,size,attrs);bool final_present=false;commit_record final_commit{};if(!read_commit(commit_final,final_present,final_commit))return failure("final commit marker corrupt; materials retained");if(final_present){if(data!=state::absent)return failure("journal missing with pending transaction data; materials retained");if(files.remove(commit_final)!=0||files.sync()!=0)return failure("final commit cleanup failed");sdk::print("xypm-recover: committed transaction cleaned\n");return 0;}if(data==state::absent){sdk::print("xypm-recover: no transaction\n");return 0;}if(!clean_unpublished_preparation())return failure("unpublished preparation corrupt; materials retained");sdk::print("xypm-recover: unpublished preparation cleaned\n");return 0;}
    if(marker_state!=state::present)return failure("cannot inspect journal; materials retained");
    if(!load_journal())return failure("journal missing, corrupt or unsupported; materials retained");
    bool was_applying=false;if(!read_stamp(applying,applying_magic,was_applying))return failure("applying marker corrupt; materials retained");
    bool committed_state=false;if(!commit_status(committed_state))return failure("commit marker corrupt; materials retained");
    if(!preflight(committed_state))return failure("recovery material or destination differs; materials retained");
    if(!committed_state&&!rollback())return failure("rollback failed; retry recovery");
    if(!cleanup(committed_state))return failure("cleanup failed; recovery remains required");
    sdk::print(committed_state?"xypm-recover: committed transaction cleaned\n":"xypm-recover: transaction rolled back\n");
#ifdef XYP_RECOVERY_TEST
    sdk::print("xypm-recover-test: checkpoints=");sdk::decimal(recovery_checkpoint_count);sdk::print("\n");
#endif
    return 0;
}
