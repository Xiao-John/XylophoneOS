// SPDX-License-Identifier: Apache-2.0
// P1 read-only installed-package index; mutating guest operations are P2.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <sys/stat.h>
#include <xos/text.hpp>
namespace {
constexpr const char* index_path="/var/lib/xypm/index.tsv";
constexpr const char* db_path="/var/lib/xypm/db.json";
struct row { char* fields[5]; };
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
}
int main(int argc,char** argv) {
    if (argc==2&&!std::strcmp(argv[1],"--version")) {std::puts("xypm 0.1 (P1 read-only guest)");return 0;}
    if (argc==1 || (argc==2&&!std::strcmp(argv[1],"--help"))) {
        std::puts("xypm list | info <package-id> | --version\nRead-only package index. Install/upgrade/remove use the host offline xypm tool.\nIndex display does not verify payload integrity.");return 0;
    }
    if (argc==2&&!std::strcmp(argv[1],"list")) return query(nullptr);
    if (argc==3&&!std::strcmp(argv[1],"info")&&identifier(argv[2])) return query(argv[2]);
    std::fputs("xypm: unsupported command or arguments; use --help\n",stderr);return 2;
}
