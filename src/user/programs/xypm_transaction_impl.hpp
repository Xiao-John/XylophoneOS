// SPDX-License-Identifier: Apache-2.0
// Included inside xypm's anonymous namespace after its read-only planner.
namespace transaction {
using namespace xypm_journal;
using xos::u8;
using xos::u32;
using xos::u64;
using xos::i64;
constexpr char prep_dir[]="/var/lib/xypm/txprep";
constexpr char prep_stamp[]="/var/lib/xypm/txprep/prepare";
constexpr size_t metadata_limit=1u<<20;
struct item { record journal; xypm_native::value* incoming; };
struct package_view { const char* id; xypm_native::value* manifest; const char* sha; };
item items[max_records]{};
directory created[max_directories]{};
package_view packages[64]{};
char db_data[metadata_limit+1], index_data[metadata_limit+1];
size_t item_count,created_count,package_count,db_length,index_length;
xos::file::Client files;
FILE* held_package;
unsigned char io_buffer[2048];
#ifdef XYP_TEST_FAULTS
unsigned fault_after,checkpoint_count;
void checkpoint(){++checkpoint_count;if(fault_after==checkpoint_count){std::printf("xypm-test: injected=%u\n",checkpoint_count);std::fflush(stdout);(void)files.sync();xos::sdk::exit(70);}}
#else
void checkpoint(){}
#endif

void must(bool value,const char* message){xypm_native::require(value,message);}
int compare_items(const void* a,const void* b){return xypm_native::compare_fold(static_cast<const item*>(a)->journal.path,static_cast<const item*>(b)->journal.path);}
int compare_dirs(const void* a,const void* b){return xypm_native::compare_fold(static_cast<const directory*>(a)->path,static_cast<const directory*>(b)->path);}
int compare_packages(const void* a,const void* b){return std::strcmp(static_cast<const package_view*>(a)->id,static_cast<const package_view*>(b)->id);}
void copy_path(char* out,size_t size,const char* source){size_t n=std::strlen(source);must(n<size,"transaction path is too long");std::memcpy(out,source,n+1);}
void absolute_path(char* out,const char* relative){size_t n=std::strlen(relative);must(n+2<=256,"destination path exceeds file-service limit");out[0]='/';std::memcpy(out+1,relative,n+1);}
void digest_from_hex(const char* text,u8* out){for(unsigned i=0;i<32;++i){auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};out[i]=static_cast<u8>((digit(text[i*2])<<4)|digit(text[i*2+1]));}}
void numbered(char* out,const char* parent,size_t index){size_t n=std::strlen(parent);std::memcpy(out,parent,n);out[n++]='/';for(int i=7;i>=0;--i){out[n+i]=char('0'+index%10);index/=10;}out[n+8]=0;}
struct writer {
    char* data;size_t capacity,used;
    void byte(char value){must(used<capacity,"transaction metadata exceeds 1 MiB");data[used++]=value;}
    void raw(const char* value){while(*value)byte(*value++);}
    void quoted(const char* value){static const char hex[]="0123456789abcdef";byte('"');for(const unsigned char* p=reinterpret_cast<const unsigned char*>(value);*p;++p){unsigned char c=*p;if(c=='"'||c=='\\'){byte('\\');byte(char(c));}else if(c<32){raw("\\u00");byte(hex[c>>4]);byte(hex[c&15]);}else byte(char(c));}byte('"');}
    void number(unsigned value){char digits[10];unsigned count=0;do{digits[count++]=char('0'+value%10);value/=10;}while(value);while(count)byte(digits[--count]);}
    void json(xypm_native::value* value){using xypm_native::kind;must(value!=nullptr,"invalid database value");switch(value->type){
        case kind::string:quoted(value->text);break;case kind::number:must(value->number>=0&&uint64_t(value->number)<=0xffffffffu,"unsupported metadata number");number(static_cast<unsigned>(value->number));break;
        case kind::array:byte('[');for(auto* p=value->child;p;p=p->next){if(p!=value->child)byte(',');json(p);}byte(']');break;
        case kind::object:byte('{');for(auto* p=value->child;p;p=p->next){if(p!=value->child)byte(',');quoted(p->key);byte(':');json(p);}byte('}');break;
        case kind::boolean:raw(value->boolean?"true":"false");break;case kind::null_value:raw("null");break;}}
};
void index_text(writer& out,const char* value){static const char hex[]="0123456789abcdef";for(const unsigned char* p=reinterpret_cast<const unsigned char*>(value);*p;++p){if(*p=='\\'){out.byte('\\');out.byte('\\');}else if(*p<32||*p==127){out.raw("\\x");out.byte(hex[*p>>4]);out.byte(hex[*p&15]);}else out.byte(char(*p));}}
void add_created(const char* absolute,u32 flags){for(size_t i=0;i<created_count;++i)if(xypm_native::ascii_equal_fold(created[i].path,absolute)){created[i].flags|=flags;return;}must(created_count<max_directories,"transaction directory limit exceeded");directory& entry=created[created_count++];entry={};copy_path(entry.path,256,absolute);entry.flags=flags;}
void discover_directories(xypm_native::value* manifest){for(auto* file=xypm_native::field(manifest,"files")->child;file;file=file->next){char path[256];absolute_path(path,xypm_native::field(file,"path")->text);for(char* p=path+1;*p;++p)if(*p=='/'){*p=0;struct stat st{};if(stat(path,&st)==0)must(S_ISDIR(st.st_mode),"destination parent is not a directory");else{must(errno==ENOENT,"cannot inspect destination parent");add_created(path,remove_on_rollback);}*p='/';}}}
void collect_packages(const char* id,xypm_native::value* replacement,const char* sha){package_count=0;for(size_t i=0;i<installed_count;++i)if(std::strcmp(installed[i].id,id)!=0)packages[package_count++]={installed[i].id,installed[i].manifest,installed[i].sha};if(replacement){must(package_count<64,"package limit exceeded");packages[package_count++]={id,replacement,sha};}std::qsort(packages,package_count,sizeof(packages[0]),compare_packages);}
bool directory_referenced(const char* relative){for(size_t i=0;i<package_count;++i)for(auto* p=xypm_native::field(packages[i].manifest,"files")->child;p;p=p->next)if(xypm_native::path_prefix(relative,xypm_native::field(p,"path")->text))return true;return false;}
void collect_unused_directories(){auto* old=installed_database?xypm_native::field(installed_database,"created_directories"):nullptr;if(old)for(auto* p=old->child;p;p=p->next)if(!directory_referenced(p->text)){char path[256];absolute_path(path,p->text);add_created(path,remove_after_commit);}std::qsort(created,created_count,sizeof(created[0]),compare_dirs);}
void generate_metadata(){
    writer index{index_data,metadata_limit,0};index.raw("xypm-index-v1\n");
    for(size_t i=0;i<package_count;++i){auto& item=packages[i];index_text(index,item.id);index.byte('\t');index_text(index,xypm_native::field(item.manifest,"upstream_version")->text);index.byte('\t');index.number(static_cast<unsigned>(xypm_native::field(item.manifest,"revision")->number));index.byte('\t');index_text(index,item.sha);index.byte('\t');index_text(index,xypm_native::field(item.manifest,"target_profile")->text);index.byte('\n');}index_length=index.used;
    xypm_native::sha256 hash;hash.update(index_data,index_length);u8 digest[32];char digest_text[65];hash.finish(digest);xypm_native::hex_digest(digest,digest_text);
    writer db{db_data,metadata_limit,0};db.raw("{\"format_version\":1,\"target_profile\":");db.quoted(XYP_PACKAGE_PROFILE_ID);db.raw(",\"packages\":{");
    for(size_t i=0;i<package_count;++i){if(i)db.byte(',');db.quoted(packages[i].id);db.raw(":{\"sha256\":");db.quoted(packages[i].sha);db.raw(",\"manifest\":");db.json(packages[i].manifest);db.byte('}');}
    db.raw("},\"created_directories\":[");bool first=true;size_t directory_total=0;auto* old_dirs=installed_database?xypm_native::field(installed_database,"created_directories"):nullptr;
    if(old_dirs)for(auto* p=old_dirs->child;p;p=p->next)if(directory_referenced(p->text)){must(++directory_total<=max_directories,"installed directory limit exceeded");if(!first)db.byte(',');db.quoted(p->text);first=false;}
    for(size_t i=0;i<created_count;++i)if(created[i].flags&remove_on_rollback){const char* rel=created[i].path+1;bool already=false;if(old_dirs)for(auto* p=old_dirs->child;p;p=p->next)if(xypm_native::ascii_equal_fold(p->text,rel)&&directory_referenced(p->text))already=true;if(!already){must(++directory_total<=max_directories,"installed directory limit exceeded");if(!first)db.byte(',');db.quoted(rel);first=false;}}
    db.raw("],\"index_sha256\":");db.quoted(digest_text);db.raw("}\n");db_length=db.used;
}
void set_digest(const void* data,size_t size,u8 out[32]){xypm_native::sha256 hash;hash.update(data,size);hash.finish(out);}
void collect_items(const char* id,xypm_native::value* replacement){
    item_count=0;installed_record* previous=find_installed(id,installed_count);
    if(previous)for(auto* p=xypm_native::field(previous->manifest,"files")->child;p;p=p->next){must(item_count<max_records,"transaction record limit exceeded");item& entry=items[item_count++];entry={};absolute_path(entry.journal.path,xypm_native::field(p,"path")->text);entry.journal.flags=old_present;entry.journal.old_size=static_cast<u32>(xypm_native::field(p,"size")->number);digest_from_hex(xypm_native::field(p,"sha256")->text,entry.journal.old_hash);}
    std::qsort(items,item_count,sizeof(items[0]),compare_items);size_t old_count=item_count;
    if(replacement)for(auto* p=xypm_native::field(replacement,"files")->child;p;p=p->next){char path[256];absolute_path(path,xypm_native::field(p,"path")->text);size_t low=0,high=old_count;while(low<high){size_t mid=low+(high-low)/2;if(xypm_native::compare_fold(items[mid].journal.path,path)<0)low=mid+1;else high=mid;}item* entry=nullptr;if(low<old_count&&xypm_native::ascii_equal_fold(items[low].journal.path,path))entry=&items[low];else{must(item_count<max_records,"transaction record limit exceeded");entry=&items[item_count++];*entry={};copy_path(entry->journal.path,256,path);}entry->journal.flags|=new_present;entry->journal.new_size=static_cast<u32>(xypm_native::field(p,"size")->number);digest_from_hex(xypm_native::field(p,"sha256")->text,entry->journal.new_hash);entry->incoming=p;}
    const char* metadata_paths[]={db_path,index_path};
    for(const char* path:metadata_paths){must(item_count<max_records,"transaction record limit exceeded");item& entry=items[item_count++];entry={};copy_path(entry.journal.path,256,path);entry.journal.flags=new_present;const bool database=std::strcmp(path,db_path)==0;const char* data=database?db_data:index_data;size_t length=database?db_length:index_length;entry.journal.new_size=static_cast<u32>(length);set_digest(data,length,entry.journal.new_hash);
        u32 size=0,attributes=0;i64 status=files.stat_info(path,size,attributes);if(status==0){must(!(attributes&xos::file::stat_is_directory)&&size<=metadata_limit,"existing package metadata invalid");entry.journal.flags|=old_present;entry.journal.old_size=size;u32 handle=0,opened=0,v=0;must(files.open(path,xos::file::read_only,handle,opened,v)==0&&opened==size,"cannot open old package metadata");xypm_native::sha256 hash;u32 remaining=size;while(remaining){u32 amount=remaining>sizeof(io_buffer)?sizeof(io_buffer):remaining;i64 n=files.read(handle,io_buffer,amount);must(n>0,"cannot read old package metadata");hash.update(io_buffer,static_cast<size_t>(n));remaining-=static_cast<u32>(n);}must(files.close(handle)==0,"cannot close old package metadata");hash.finish(entry.journal.old_hash);}else must(status==static_cast<i64>(xos::file::status::not_found),"cannot inspect old package metadata");}
    std::qsort(items,item_count,sizeof(items[0]),compare_items);for(size_t i=1;i<item_count;++i)must(xypm_native::compare_fold(items[i-1].journal.path,items[i].journal.path)<0,"duplicate transaction destination");
}
void write_handle(u32 handle,const void* source,size_t length){const auto* bytes=static_cast<const u8*>(source);size_t offset=0;while(offset<length){u32 amount=static_cast<u32>(length-offset>sizeof(io_buffer)?sizeof(io_buffer):length-offset);i64 n=files.write(handle,bytes+offset,amount);must(n>0,"transaction write failed");offset+=static_cast<size_t>(n);}}
u32 create_file(const char* path){u32 h=0,size=0,v=0;must(files.open(path,xos::file::write_only|xos::file::open_create|xos::file::open_exclusive,h,size,v)==0,"cannot create transaction file");return h;}
void write_file(const char* path,const void* bytes,size_t length){u32 h=create_file(path);write_handle(h,bytes,length);must(files.close(h)==0,"cannot close transaction file");}
bool absent(const char* path){u32 size=0,attrs=0;i64 result=files.stat_info(path,size,attrs);must(result==0||result==static_cast<i64>(xos::file::status::not_found),"cannot inspect transaction path");return result!=0;}
void ensure_directory(const char* path){u32 size=0,attrs=0;i64 result=files.stat_info(path,size,attrs);if(result==0)must((attrs&xos::file::stat_is_directory)!=0,"transaction parent is not a directory");else{must(result==static_cast<i64>(xos::file::status::not_found),"cannot inspect transaction parent");must(files.mkdir(path)==0,"cannot create transaction parent");checkpoint();}}
void cleanup_old_preparation(){
    if(absent(prep_dir))return;
    xos::file::entry entries[4]{};u32 count=0,cursor=0;must(files.list(prep_dir,entries,4,count,cursor)==0&&cursor==0&&count<=1,"stale preparation contains unexpected files");
    if(count){must(!entries[0].directory&&std::strcmp(entries[0].name,"prepare")==0,"stale preparation contains unknown data");u8 stamp[8];u32 length=0;must(files.read_all(prep_stamp,stamp,sizeof(stamp),length)==0&&length==8&&!std::memcmp(stamp,prepare_magic,8),"stale preparation marker is invalid");must(files.remove(prep_stamp)==0,"cannot clean stale preparation marker");}
    must(files.remove(prep_dir)==0&&files.sync()==0,"cannot clean stale preparation");
}
void begin_preparation(){
    ensure_directory("/var");ensure_directory("/var/lib");ensure_directory("/var/lib/xypm");
    must(absent(marker)&&absent(data_dir)&&absent(commit_final),"unfinished transaction requires recovery");cleanup_old_preparation();
    must(files.mkdir(prep_dir)==0,"cannot create transaction preparation");checkpoint();write_file(prep_stamp,prepare_magic,8);must(files.sync()==0,"cannot sync preparation marker");checkpoint();
    must(files.rename(prep_dir,data_dir)==0&&files.sync()==0,"cannot publish preparation marker");checkpoint();
    must(files.mkdir(old_dir)==0,"cannot create backup directory");checkpoint();must(files.mkdir(new_dir)==0&&files.sync()==0,"cannot create staging directory");checkpoint();
}
void copy_old(const item& entry,const char* destination){u32 source=0,size=0,v=0;must(files.open(entry.journal.path,xos::file::read_only,source,size,v)==0&&size==entry.journal.old_size,"cannot open managed file for backup");u32 target=create_file(destination);xypm_native::sha256 hash;u32 remaining=size;bool first=true;while(remaining){u32 amount=remaining>sizeof(io_buffer)?sizeof(io_buffer):remaining;i64 n=files.read(source,io_buffer,amount);must(n>0,"cannot read managed file for backup");hash.update(io_buffer,static_cast<size_t>(n));write_handle(target,io_buffer,static_cast<size_t>(n));remaining-=static_cast<u32>(n);if(first){first=false;checkpoint();}}must(files.close(source)==0&&files.close(target)==0,"cannot close backup files");u8 digest[32];hash.finish(digest);must(!std::memcmp(digest,entry.journal.old_hash,32),"managed file changed during backup");}
void copy_new(const item& entry,const char* destination,FILE* source){
    u32 target=create_file(destination);xypm_native::sha256 hash;u32 remaining=entry.journal.new_size;
    if(entry.incoming){must(source&&entry.incoming->payload_offset<=LONG_MAX&&std::fseek(source,static_cast<long>(entry.incoming->payload_offset),SEEK_SET)==0,"cannot seek held package");bool first=true;while(remaining){size_t amount=remaining>sizeof(io_buffer)?sizeof(io_buffer):remaining;size_t n=std::fread(io_buffer,1,amount,source);must(n==amount,"cannot read held package");hash.update(io_buffer,n);write_handle(target,io_buffer,n);remaining-=static_cast<u32>(n);if(first){first=false;checkpoint();}}}
    else{const bool database=std::strcmp(entry.journal.path,db_path)==0;const char* data=database?db_data:index_data;size_t length=database?db_length:index_length;must(length==remaining,"metadata staging size mismatch");hash.update(data,length);write_handle(target,data,length);checkpoint();}
    must(files.close(target)==0,"cannot close staged file");u8 digest[32];hash.finish(digest);must(!std::memcmp(digest,entry.journal.new_hash,32),"staged content digest mismatch");
}
void stage_all(FILE* source){for(size_t i=0;i<item_count;++i){char path[80];if(items[i].journal.flags&old_present){numbered(path,old_dir,i);copy_old(items[i],path);checkpoint();}if(items[i].journal.flags&new_present){numbered(path,new_dir,i);copy_new(items[i],path,source);checkpoint();}}must(files.sync()==0,"cannot sync transaction staging");checkpoint();}
void reserve_space(xypm_native::value* manifest){size_t count=0,new_directories=0;if(manifest)for(auto* p=xypm_native::field(manifest,"files")->child;p;p=p->next)++count;for(size_t i=0;i<created_count;++i)if(created[i].flags&remove_on_rollback)++new_directories;u64 remaining=(u64(count)+u64(new_directories)*2+64)*65536;constexpr u64 limit=0xfffe0000ULL;std::memset(io_buffer,0,sizeof(io_buffer));bool first=true;for(unsigned part=0;remaining;++part){must(part<2,"transaction reserve limit exceeded");u32 handle=create_file(part?reserve2:reserve);u64 chunk=remaining>limit?limit:remaining;remaining-=chunk;while(chunk){size_t amount=chunk>sizeof(io_buffer)?sizeof(io_buffer):static_cast<size_t>(chunk);write_handle(handle,io_buffer,amount);chunk-=amount;if(first){first=false;checkpoint();}}must(files.close(handle)==0&&files.sync()==0,"cannot reserve transaction space");checkpoint();}}
void publish_journal(header& journal){journal={};std::memcpy(journal.magic,magic,8);journal.version=version;journal.record_count=static_cast<u32>(item_count);journal.directory_count=static_cast<u32>(created_count);xypm_journal::sha256 hash;hash.update(&journal,24);for(size_t i=0;i<item_count;++i)hash.update(&items[i].journal,sizeof(record));for(size_t i=0;i<created_count;++i)hash.update(&created[i],sizeof(directory));hash.finish(journal.digest);
    u32 h=create_file(journal_temp);write_handle(h,&journal,sizeof(journal));checkpoint();for(size_t i=0;i<item_count;++i)write_handle(h,&items[i].journal,sizeof(record));for(size_t i=0;i<created_count;++i)write_handle(h,&created[i],sizeof(directory));must(files.close(h)==0&&files.sync()==0,"cannot sync transaction journal");checkpoint();must(files.rename(journal_temp,marker)==0&&files.sync()==0,"cannot publish transaction journal");checkpoint();}
void apply_all(){
    write_file(applying,applying_magic,8);must(files.sync()==0,"cannot sync applying marker");checkpoint();must(files.remove(reserve)==0,"cannot release transaction reserve");if(!absent(reserve2))must(files.remove(reserve2)==0,"cannot release transaction reserve");must(files.sync()==0,"cannot sync released reserve");checkpoint();
    for(size_t i=0;i<created_count;++i)if(created[i].flags&remove_on_rollback){must(files.mkdir(created[i].path)==0&&files.sync()==0,"cannot create package directory");checkpoint();}
    for(size_t i=0;i<item_count;++i){const record& entry=items[i].journal;if(entry.flags&old_present){must(files.remove(entry.path)==0&&files.sync()==0,"cannot remove old package file");
#ifdef XYP_TEST_FAULTS
        if(std::strcmp(entry.path,"/usr/bin/xypm")==0){std::printf("xypm-test: self_removed=%u\n",checkpoint_count+1);std::fflush(stdout);}
#endif
        checkpoint();}if(entry.flags&new_present){char path[80];numbered(path,new_dir,i);must(files.rename(path,entry.path)==0&&files.sync()==0,"cannot install staged package file");checkpoint();}}
}
void publish_commit(const header& journal){commit_record commit{};std::memcpy(commit.magic,commit_magic,8);std::memcpy(commit.journal_hash,journal.digest,32);xypm_journal::sha256 hash;hash.update(&commit,40);hash.finish(commit.self_hash);write_file(commit_temp,&commit,sizeof(commit));must(files.sync()==0,"cannot sync commit record");checkpoint();must(files.rename(commit_temp,committed)==0&&files.sync()==0,"cannot publish commit record");checkpoint();}
int run(const char* operation,const char* target,unsigned injected=0,const char* expected_sha=nullptr){
#ifdef XYP_TEST_FAULTS
    fault_after=injected;checkpoint_count=0;
#else
    (void)injected;
#endif
    if(!files.init()||xypm_acquire_maintenance()!=0){std::fputs("xypm: maintenance write lease required\n",stderr);return 3;}
    const char* recovery_abi=std::getenv("XYP_RECOVERY_ABI");
    if(!recovery_abi||std::strcmp(recovery_abi,"1")!=0){std::fputs("xypm: compatible immutable recovery image required\n",stderr);return 3;}
    held_package=nullptr;xypm_native::verified_package package{};bool removing=std::strcmp(operation,"remove")==0;
    if(removing){if(!xypm_native::identifier(target)||plan_remove(target,true)!=0)return 3;}
    else if(plan_package(operation,target,&held_package,&package,true,expected_sha)!=0)return 3;
    const char* id=removing?target:xypm_native::field(package.manifest,"id")->text;
    jmp_buf recovery;xypm_native::error_target=&recovery;
    if(setjmp(recovery)!=0){xypm_native::error_target=nullptr;if(held_package){std::fclose(held_package);held_package=nullptr;}std::fprintf(stderr,"xypm: transaction stopped: %s; recovery may be required\n",xypm_native::last_error);return 3;}
    created_count=0;if(!removing)discover_directories(package.manifest);collect_packages(id,removing?nullptr:package.manifest,removing?nullptr:package.digest);collect_unused_directories();generate_metadata();collect_items(id,removing?nullptr:package.manifest);
    begin_preparation();stage_all(held_package);if(held_package){int close_result=std::fclose(held_package);held_package=nullptr;must(close_result==0,"cannot close held package");}reserve_space(removing?nullptr:package.manifest);
    header journal{};publish_journal(journal);apply_all();publish_commit(journal);
    xypm_native::error_target=nullptr;std::printf("xypm: %s %s committed; completing recovery cleanup\n",operation,id);
#ifdef XYP_TEST_FAULTS
    std::printf("xypm-test: checkpoints=%u\n",checkpoint_count);
#endif
    return 0;
}
}
