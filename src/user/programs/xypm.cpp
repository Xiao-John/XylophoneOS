// SPDX-License-Identifier: Apache-2.0
// P2-2 read-only package verification and install/upgrade planning; mutations remain gated.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <sys/stat.h>
#include <xos/text.hpp>
#include <xos/file_client.hpp>
#include "xypm_profile.hpp"
#include "xypm_native.hpp"
namespace {
constexpr const char* index_path="/var/lib/xypm/index.tsv";
constexpr const char* db_path="/var/lib/xypm/db.json";
struct row { char* fields[5]; };
struct installed_record { char id[81]; char sha[65]; xypm_native::value* manifest; };
struct owned_record { char path[256]; char owner[81]; xypm_native::value* file; };
installed_record installed[64];
owned_record owned[8192];
size_t installed_owned_count;
char expected_index[1u<<20];
bool identifier(const char* value) {
    const size_t size=std::strlen(value);
    if (!size || size>80 || value[0]<'a' || value[0]>'z') return false;
    for (size_t i=0;i<size;++i) {
        char c=value[i];
        if (!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='.'||c=='-')) return false;
    }
    return true;
}
bool valid(row& item) {
    if (!identifier(item.fields[0]) || !identifier(item.fields[4])) return false;
    if (!xos::text::valid(item.fields[1],static_cast<xos::u32>(std::strlen(item.fields[1])))) return false;
    if (!*item.fields[1] || std::strlen(item.fields[1])>6144 || std::strlen(item.fields[3])!=64) return false;
    for (char* p=item.fields[1];*p;++p) if (static_cast<unsigned char>(*p)<32 || *p==127) return false;
    for (char* p=item.fields[3];*p;++p) if (!((*p>='0'&&*p<='9')||(*p>='a'&&*p<='f'))) return false;
    if (!*item.fields[2] || std::strlen(item.fields[2])>10) return false;
    for (char* p=item.fields[2];*p;++p) if (*p<'0'||*p>'9') return false;
    return std::strtoul(item.fields[2],nullptr,10)<=2147483647ul;
}
int query(const char* wanted) {
    const char* legacy_paths[]={"/var/lib/xpm/db.json","/var/lib/xpm/index.tsv",
                                "/var/lib/xpkg/db.json","/var/lib/xpkg/index.tsv"};
    for (const char* path:legacy_paths) {
        struct stat legacy{};
        if (stat(path,&legacy)==0 || errno!=ENOENT) {
            std::fputs("xypm: legacy package database or unreadable path; migrate a copy first\n",stderr);
            return 3;
        }
    }
    FILE* file=std::fopen(index_path,"rb");
    if (!file) {
        int error=errno;struct stat db{};
        if (error==ENOENT && stat(db_path,&db)!=0 && errno==ENOENT) {
            if (wanted) {std::fputs("xypm: package not installed\n",stderr);return 1;}
            std::puts("No packages installed.");return 0;
        }
        std::fputs("xypm: cannot read package index\n",stderr);return 3;
    }
    constexpr size_t limit=1024*1024;
    char* data=static_cast<char*>(std::malloc(limit+1));
    if (!data) {std::fclose(file);std::fputs("xypm: out of memory\n",stderr);return 3;}
    size_t used=0;
    while (used<=limit) {
        size_t got=std::fread(data+used,1,limit+1-used,file);used+=got;
        if (!got || used>limit) break;
    }
    bool failed=std::ferror(file)!=0;int closed=std::fclose(file);
    if (failed||closed||used>limit||std::memchr(data,0,used)||used<13||data[used-1]!='\n') {
        std::free(data);std::fputs("xypm: corrupt package index\n",stderr);return 3;
    }
    data[used]=0;row rows[64]{};size_t count=0;char* cursor=std::strchr(data,'\n');
    if (!cursor) {std::free(data);return 3;}*cursor++=0;
    bool okay=std::strcmp(data,"xypm-index-v1")==0;
    while (okay&&*cursor) {
        if (count==64) {okay=false;break;}
        row& item=rows[count];
        for (unsigned i=0;i<5;++i) {
            item.fields[i]=cursor;char* end=std::strchr(cursor,i==4?'\n':'\t');
            if (!end) {okay=false;break;}
            if (i<4 && std::memchr(cursor,'\n',size_t(end-cursor))) {okay=false;break;}
            if (i==4 && std::memchr(cursor,'\t',size_t(end-cursor))) {okay=false;break;}
            *end=0;cursor=end+1;
        }
        if (!okay||!valid(item)) {okay=false;break;}
        for (size_t i=0;i<count;++i) if (!std::strcmp(rows[i].fields[0],item.fields[0])) okay=false;
        ++count;
    }
    if (!okay) {std::free(data);std::fputs("xypm: corrupt package index\n",stderr);return 3;}
    bool found=false;
    for (size_t i=0;i<count;++i) {
        auto& f=rows[i].fields;
        if (wanted&&std::strcmp(wanted,f[0])) continue;
        found=true;
        if (wanted) std::printf("id: %s\nversion: %s\nrevision: %s\nsha256: %s\nprofile: %s\n",f[0],f[1],f[2],f[3],f[4]);
        else std::printf("%s %s-r%s\n",f[0],f[1],f[2]);
    }
    if (!wanted&&!count) std::puts("No packages installed.");
    std::free(data);
    if (wanted&&!found) {std::fputs("xypm: package not installed\n",stderr);return 1;}
    return 0;
}
int verify_package_path(const char* path,xypm_native::verified_package* output=nullptr,bool quiet=false,const char* expected_sha=nullptr) {
    FILE* file=std::fopen(path,"rb");
    if(!file){std::fputs("xypm: cannot open package\n",stderr);return 3;}
    if(std::fseek(file,0,SEEK_END)!=0){std::fclose(file);std::fputs("xypm: cannot seek package\n",stderr);return 3;}
    long end=std::ftell(file);
    if(end<0){std::fclose(file);std::fputs("xypm: cannot size package\n",stderr);return 3;}
    jmp_buf recovery;
    xypm_native::error_target=&recovery;
    if(setjmp(recovery)!=0){xypm_native::error_target=nullptr;std::fclose(file);std::fprintf(stderr,"xypm: invalid package: %s\n",xypm_native::last_error);return 3;}
    xypm_native::verified_package result=xypm_native::verify_package(file,static_cast<uint64_t>(end));
    xypm_native::error_target=nullptr;
    if(std::fclose(file)!=0){std::fputs("xypm: package close failed\n",stderr);return 3;}
    if(expected_sha&&(!xypm_native::hash_text(expected_sha)||std::strcmp(expected_sha,result.digest)!=0)){std::fputs("xypm: package SHA-256 mismatch\n",stderr);return 3;}
    if(output)*output=result;
    if(!quiet)std::printf("Package verified: %s\nFiles: %u\nSHA-256: %s\n",
                          xypm_native::field(result.manifest,"id")->text,result.files,result.digest);
    return 0;
}
void copy_text(char* target,size_t capacity,const char* source){size_t n=std::strlen(source);xypm_native::require(n<capacity,"database value too long");std::memcpy(target,source,n+1);}
void check_legacy_databases(){const char* paths[]={"/var/lib/xpm/db.json","/var/lib/xpm/index.tsv","/var/lib/xpkg/db.json","/var/lib/xpkg/index.tsv"};for(const char* path:paths){struct stat st{};if(stat(path,&st)==0||errno!=ENOENT)xypm_native::require(false,"legacy package database or unreadable path");}}
char* read_bounded(const char* path,size_t limit,size_t& length){FILE* file=std::fopen(path,"rb");if(!file)return nullptr;if(std::fseek(file,0,SEEK_END)!=0){std::fclose(file);return nullptr;}long end=std::ftell(file);if(end<0||size_t(end)>limit||std::fseek(file,0,SEEK_SET)!=0){std::fclose(file);return nullptr;}char* data=static_cast<char*>(std::malloc(size_t(end)+1));if(!data){std::fclose(file);return nullptr;}length=std::fread(data,1,size_t(end),file);bool close_ok=std::fclose(file)==0;if(length!=size_t(end)||!close_ok){std::free(data);return nullptr;}data[length]=0;return data;}
bool path_exists(const char* path,struct stat& st){if(stat(path,&st)==0)return true;return errno!=ENOENT;}
void hash_path(const char* path,uint64_t expected_size,const char* expected_hash){FILE* file=std::fopen(path,"rb");xypm_native::require(file!=nullptr,"installed package file is missing or unreadable");xypm_native::sha256 hash;uint8_t buffer[32768];uint64_t total=0;for(;;){size_t n=std::fread(buffer,1,sizeof(buffer),file);if(n){hash.update(buffer,n);total+=n;}if(n<sizeof(buffer)){if(std::ferror(file))xypm_native::require(false,"installed package file read error");break;}}bool closed=std::fclose(file)==0;xypm_native::require(closed&&total==expected_size,"installed package file size changed");uint8_t digest[32];char text_hash[65];hash.finish(digest);xypm_native::hex_digest(digest,text_hash);xypm_native::require(std::strcmp(text_hash,expected_hash)==0,"installed package file was modified");}
void append_index(char c,size_t& used){xypm_native::require(used+1<sizeof(expected_index),"xypm index exceeds 1 MiB");expected_index[used++]=c;}
void append_index_text(const char* text,size_t& used){for(const unsigned char* p=reinterpret_cast<const unsigned char*>(text);*p;++p){if(*p=='\\'){append_index('\\',used);append_index('\\',used);}else if(*p<32||*p==127){static const char hex[]="0123456789abcdef";append_index('\\',used);append_index('x',used);append_index(hex[*p>>4],used);append_index(hex[*p&15],used);}else append_index(char(*p),used);}}
int compare_installed(const void* left,const void* right){return std::strcmp(static_cast<const installed_record*>(left)->id,static_cast<const installed_record*>(right)->id);}
int compare_owned(const void* left,const void* right){return xypm_native::compare_fold(static_cast<const owned_record*>(left)->path,static_cast<const owned_record*>(right)->path);}
owned_record* find_owned(const char* path,size_t count){size_t low=0,high=count;while(low<high){size_t mid=low+(high-low)/2;if(xypm_native::compare_fold(owned[mid].path,path)<0)low=mid+1;else high=mid;}return low<count&&xypm_native::ascii_equal_fold(owned[low].path,path)?&owned[low]:nullptr;}
bool canonical_component_path(const char* absolute);
void validate_planned_cycles(const char* id,xypm_native::value* manifest,size_t count,bool adding);
size_t load_installed_database(){
    check_legacy_databases();struct stat db_stat{},index_stat{};bool has_db=stat(db_path,&db_stat)==0;int db_error=errno;bool has_index=stat(index_path,&index_stat)==0;int index_error=errno;xypm_native::require(has_db||db_error==ENOENT,"cannot inspect installed database");xypm_native::require(has_index||index_error==ENOENT,"cannot inspect installed index");if(!has_db&&!has_index)return 0;xypm_native::require(has_db&&has_index,"orphan installed database or index");
    size_t db_size=0,index_size=0;char* db_bytes=read_bounded(db_path,1u<<20,db_size);char* index_bytes=read_bounded(index_path,1u<<20,index_size);xypm_native::require(db_bytes&&index_bytes,"installed database or index unreadable/too large");
    xypm_native::json_parser parser(db_bytes,db_size,1);xypm_native::value* db=parser.parse();
    static const char* const db_fields[]={"format_version","target_profile","packages","created_directories","index_sha256"};xypm_native::exact_fields(db,db_fields,5);
    xypm_native::require(xypm_native::unsigned_number(xypm_native::field(db,"format_version"),1,"invalid database version")==1,"invalid database version");
    const char* profile=xypm_native::text(xypm_native::need(db,"target_profile",xypm_native::kind::string),"database profile",80);xypm_native::require(std::strcmp(profile,XYP_PACKAGE_PROFILE_ID)==0,"installed database profile mismatch");
    const char* binding=xypm_native::text(xypm_native::need(db,"index_sha256",xypm_native::kind::string),"index digest",64);xypm_native::require(xypm_native::hash_text(binding),"invalid index digest");
    xypm_native::value* dirs=xypm_native::need(db,"created_directories",xypm_native::kind::array);size_t dir_count=0;for(auto* d=dirs->child;d;d=d->next){++dir_count;xypm_native::require(dir_count<=32768&&d->type==xypm_native::kind::string&&xypm_native::directory_path(d->text),"invalid created-directory list");const char* p=d->text;bool managed=std::strcmp(p,"usr")==0;const char* roots[]={"usr/bin","usr/lib","usr/share"};for(const char* root:roots)if(std::strcmp(p,root)==0||(std::strncmp(p,root,std::strlen(root))==0&&p[std::strlen(root)]=='/'))managed=true;xypm_native::require(managed,"created directory outside managed roots");for(auto* q=dirs->child;q!=d;q=q->next)xypm_native::require(!xypm_native::ascii_equal_fold(q->text,p),"duplicate created directory");}
    xypm_native::value* packages=xypm_native::need(db,"packages",xypm_native::kind::object);size_t count=0,owned_count=0;
    for(auto* p=packages->child;p;p=p->next){xypm_native::require(count<64&&p->key&&xypm_native::identifier(p->key),"invalid installed package count or id");auto& record=installed[count++];copy_text(record.id,sizeof(record.id),p->key);static const char* const rec_fields[]={"sha256","manifest"};xypm_native::exact_fields(p,rec_fields,2);const char* sha=xypm_native::text(xypm_native::need(p,"sha256",xypm_native::kind::string),"package digest",64);xypm_native::require(xypm_native::hash_text(sha),"invalid package digest");copy_text(record.sha,sizeof(record.sha),sha);record.manifest=xypm_native::need(p,"manifest",xypm_native::kind::object);xypm_native::validate_manifest(record.manifest);xypm_native::require(std::strcmp(xypm_native::field(record.manifest,"id")->text,record.id)==0,"database package identity mismatch");for(auto* f=xypm_native::field(record.manifest,"files")->child;f;f=f->next){xypm_native::require(owned_count<8192,"installed file ownership limit exceeded");auto& item=owned[owned_count++];copy_text(item.path,sizeof(item.path),xypm_native::field(f,"path")->text);copy_text(item.owner,sizeof(item.owner),record.id);item.file=f;}}
    std::qsort(owned,owned_count,sizeof(owned[0]),compare_owned);installed_owned_count=owned_count;for(size_t i=0;i<owned_count;++i){const char* path=owned[i].path;if(i)xypm_native::require(!xypm_native::ascii_equal_fold(owned[i-1].path,path),"duplicate installed file ownership");char prefix[256];size_t n=std::strlen(path);for(size_t j=0;j<n;++j)if(path[j]=='/'){std::memcpy(prefix,path,j);prefix[j]=0;xypm_native::require(find_owned(prefix,owned_count)==nullptr,"installed file/directory collision");}}
    std::qsort(installed,count,sizeof(installed[0]),compare_installed);
    size_t used=0;const char* header="xypm-index-v1\n";std::memcpy(expected_index,header,std::strlen(header));used=std::strlen(header);
    for(size_t i=0;i<count;++i){auto* manifest=installed[i].manifest;append_index_text(installed[i].id,used);append_index('\t',used);append_index_text(xypm_native::field(manifest,"upstream_version")->text,used);append_index('\t',used);char revision[16];std::snprintf(revision,sizeof(revision),"%lld",static_cast<long long>(xypm_native::field(manifest,"revision")->number));append_index_text(revision,used);append_index('\t',used);append_index_text(installed[i].sha,used);append_index('\t',used);append_index_text(xypm_native::field(manifest,"target_profile")->text,used);append_index('\n',used);}
    expected_index[used]=0;xypm_native::sha256 index_hash;index_hash.update(expected_index,used);uint8_t digest[32];char digest_text[65];index_hash.finish(digest);xypm_native::hex_digest(digest,digest_text);xypm_native::require(std::strcmp(digest_text,binding)==0&&used==index_size&&std::memcmp(expected_index,index_bytes,used)==0,"installed index differs from database");
    std::free(db_bytes);std::free(index_bytes);
    for(size_t i=0;i<count;++i){auto* deps=xypm_native::field(installed[i].manifest,"runtime_dependencies");for(auto* dep=deps->child;dep;dep=dep->next){const char* id=xypm_native::field(dep,"id")->text;installed_record* found=nullptr;for(size_t j=0;j<count;++j)if(std::strcmp(installed[j].id,id)==0)found=&installed[j];xypm_native::require(found!=nullptr,"installed dependency is missing");auto* m=found->manifest;xypm_native::require(std::strcmp(found->sha,xypm_native::field(dep,"sha256")->text)==0&&std::strcmp(xypm_native::field(m,"upstream_version")->text,xypm_native::field(dep,"upstream_version")->text)==0&&xypm_native::field(m,"revision")->number==xypm_native::field(dep,"revision")->number,"installed dependency lock mismatch");}}
    validate_planned_cycles("",nullptr,count,false);
    for(size_t i=0;i<owned_count;++i){char path[258];int n=std::snprintf(path,sizeof(path),"/%s",owned[i].path);xypm_native::require(n>0&&size_t(n)<sizeof(path),"owned file path too long");struct stat st{};xypm_native::require(stat(path,&st)==0&&S_ISREG(st.st_mode),"installed package file missing or not regular");xypm_native::require(canonical_component_path(path),"installed path uses a noncanonical FAT name/alias");uint64_t size=xypm_native::unsigned_number(xypm_native::field(owned[i].file,"size"),xypm_native::max_file_bytes,"invalid installed file size");xypm_native::require(uint64_t(st.st_size)==size,"installed package file size changed");hash_path(path,size,xypm_native::field(owned[i].file,"sha256")->text);}
    return count;
}
installed_record* find_installed(const char* id,size_t count){for(size_t i=0;i<count;++i)if(std::strcmp(installed[i].id,id)==0)return &installed[i];return nullptr;}
void match_dependency(xypm_native::value* dep,const char* replacing_id,xypm_native::value* replacement,const char* replacement_sha,size_t count){const char* id=xypm_native::field(dep,"id")->text;installed_record* record=std::strcmp(id,replacing_id)==0?nullptr:find_installed(id,count);xypm_native::value* manifest=record?record->manifest:nullptr;const char* sha=record?record->sha:nullptr;if(std::strcmp(id,replacing_id)==0){manifest=replacement;sha=replacement_sha;}xypm_native::require(manifest&&sha,"package dependency is missing");xypm_native::require(std::strcmp(sha,xypm_native::field(dep,"sha256")->text)==0&&std::strcmp(xypm_native::field(manifest,"upstream_version")->text,xypm_native::field(dep,"upstream_version")->text)==0&&xypm_native::field(manifest,"revision")->number==xypm_native::field(dep,"revision")->number,"package dependency lock mismatch");}
void validate_planned_dependencies(const char* id,xypm_native::value* manifest,const char* sha,size_t count){auto* deps=xypm_native::field(manifest,"runtime_dependencies");for(auto* dep=deps->child;dep;dep=dep->next)match_dependency(dep,id,manifest,sha,count);for(size_t i=0;i<count;++i)if(std::strcmp(installed[i].id,id)!=0){auto* old_deps=xypm_native::field(installed[i].manifest,"runtime_dependencies");for(auto* dep=old_deps->child;dep;dep=dep->next)match_dependency(dep,id,manifest,sha,count);}}
size_t prospective_index(const char* id,const char* replace_id,size_t count,bool adding){if(std::strcmp(id,replace_id)==0){installed_record* old=find_installed(id,count);return old?size_t(old-installed):count;}installed_record* old=find_installed(id,count);return old?size_t(old-installed):SIZE_MAX;}
void visit_dependency_graph(size_t index,const char* replace_id,xypm_native::value* replacement,size_t count,bool adding,uint8_t* states){size_t total=count+(adding?1:0);xypm_native::require(index<total,"dependency graph references missing package");if(states[index]==2)return;xypm_native::require(states[index]==0,"installed dependency cycle");states[index]=1;const char* id=index==count?replace_id:installed[index].id;xypm_native::value* manifest=std::strcmp(id,replace_id)==0?replacement:installed[index].manifest;for(auto* dep=xypm_native::field(manifest,"runtime_dependencies")->child;dep;dep=dep->next){size_t next=prospective_index(xypm_native::field(dep,"id")->text,replace_id,count,adding);xypm_native::require(next!=SIZE_MAX,"dependency graph references missing package");visit_dependency_graph(next,replace_id,replacement,count,adding,states);}states[index]=2;}
void validate_planned_cycles(const char* id,xypm_native::value* manifest,size_t count,bool adding){uint8_t states[65]{};size_t total=count+(adding?1:0);for(size_t i=0;i<total;++i)if(states[i]==0)visit_dependency_graph(i,id,manifest,count,adding,states);}
bool canonical_component_path(const char* absolute){xos::file::Client client;if(!client.init())return false;char prefix[257]="/";const char* cursor=absolute;while(*cursor=='/')++cursor;while(*cursor){const char* end=std::strchr(cursor,'/');size_t n=end?size_t(end-cursor):std::strlen(cursor);if(!n||n>100)return false;char component[101];std::memcpy(component,cursor,n);component[n]=0;char full[257];int length=std::snprintf(full,sizeof(full),"%s%s%s",prefix,std::strcmp(prefix,"/")==0?"":"/",component);if(length<0||size_t(length)>=sizeof(full))return false;struct stat st{};if(stat(full,&st)!=0){if(errno==ENOENT)return true;return false;}char parent[257];copy_text(parent,sizeof(parent),prefix);bool found=false;uint32_t page=0;for(;;){xos::file::entry entries[64]{};uint32_t count=0;int64_t result=client.list(parent,entries,64,count,page);if(result!=0)return false;for(uint32_t i=0;i<count;++i)if(xypm_native::ascii_equal_fold(entries[i].name,component))found=true;if(page==0)break;}if(!found)return false;if(end&& !S_ISDIR(st.st_mode))return false;copy_text(prefix,sizeof(prefix),full);if(!end)break;cursor=end+1;}return true;}
int plan_package(const char* operation,const char* path){
    xypm_native::verified_package package{};if(verify_package_path(path,&package,true)!=0)return 3;
    jmp_buf recovery;xypm_native::error_target=&recovery;
    if(setjmp(recovery)!=0){xypm_native::error_target=nullptr;std::fprintf(stderr,"xypm: plan rejected: %s\n",xypm_native::last_error);return 3;}
    size_t count=load_installed_database();auto* manifest=package.manifest;const char* id=xypm_native::field(manifest,"id")->text;installed_record* prior=find_installed(id,count);
    bool upgrade=std::strcmp(operation,"upgrade")==0;xypm_native::require((upgrade&&prior)||(!upgrade&&!prior),upgrade?"package is not installed; choose install":"package already installed; choose upgrade");
    validate_planned_dependencies(id,manifest,package.digest,count);
    validate_planned_cycles(id,manifest,count,prior==nullptr);
    size_t file_count=0;uint64_t total=0;
    for(auto* item=xypm_native::field(manifest,"files")->child;item;item=item->next){++file_count;const char* relative=xypm_native::field(item,"path")->text;owned_record* owner_record=find_owned(relative,installed_owned_count);const char* owner=owner_record?owner_record->owner:nullptr;xypm_native::require(!owner||std::strcmp(owner,id)==0,"destination belongs to another package");
        char absolute[258];int n=std::snprintf(absolute,sizeof(absolute),"/%s",relative);xypm_native::require(n>0&&size_t(n)<sizeof(absolute),"destination path too long");struct stat st{};if(path_exists(absolute,st)){xypm_native::require(S_ISREG(st.st_mode)&&owner&&std::strcmp(owner,id)==0,"unmanaged or directory destination already exists");}else{xypm_native::require(errno==ENOENT,"cannot inspect destination");}
        xypm_native::require(canonical_component_path(absolute),"destination uses a noncanonical FAT name/alias");
        char parent[258];copy_text(parent,sizeof(parent),absolute);for(char* p=parent+std::strlen(parent);p>parent;--p)if(*p=='/'){if(p==parent){p[1]=0;break;}*p=0;break;}struct stat parent_stat{};for(;;){if(stat(parent,&parent_stat)==0){xypm_native::require(S_ISDIR(parent_stat.st_mode),"destination parent is a file");break;}xypm_native::require(errno==ENOENT,"cannot inspect destination parent");char* slash=std::strrchr(parent,'/');if(!slash||slash==parent){std::strcpy(parent,"/");if(stat(parent,&parent_stat)!=0||!S_ISDIR(parent_stat.st_mode))xypm_native::require(false,"root directory unavailable");break;}*slash=0;}
        total+=uint64_t(xypm_native::field(item,"size")->number);
    }
    xypm_native::error_target=nullptr;
    std::printf("Plan: %s %s\nFiles: %zu\nPayload bytes: %llu\nPackage SHA-256: %s\nDependencies: %zu\nNo files changed.\n",operation,id,file_count,static_cast<unsigned long long>(total),package.digest, [&](){size_t n=0;for(auto* p=xypm_native::field(manifest,"runtime_dependencies")->child;p;p=p->next)++n;return n;}());return 0;
}
}
int main(int argc,char** argv) {
    if (argc==2&&!std::strcmp(argv[1],"--version")) {std::puts("xypm 0.2 (P2 package verification)");return 0;}
    if (argc==1 || (argc==2&&!std::strcmp(argv[1],"--help"))) {
        std::puts("xypm list | info <package-id> | verify <package.xpk> [sha256]\nxypm plan install|upgrade <package.xpk>\nRead-only package validation and plan. No files are changed.");return 0;
    }
    if (argc==2&&!std::strcmp(argv[1],"list")) return query(nullptr);
    if (argc==3&&!std::strcmp(argv[1],"info")&&identifier(argv[2])) return query(argv[2]);
    if ((argc==3||argc==4)&&!std::strcmp(argv[1],"verify")) return verify_package_path(argv[2],nullptr,false,argc==4?argv[3]:nullptr);
    if(argc==4&&!std::strcmp(argv[1],"plan")&&(!std::strcmp(argv[2],"install")||!std::strcmp(argv[2],"upgrade")))return plan_package(argv[2],argv[3]);
    std::fputs("xypm: unsupported command or arguments; use --help\n",stderr);return 2;
}
