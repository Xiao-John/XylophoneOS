// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <climits>
#include <setjmp.h>
#include <xos/text.hpp>

namespace xypm_native {
constexpr size_t max_manifest_bytes = 1u << 20;
constexpr size_t max_members = 8192;
constexpr uint64_t max_file_bytes = 64u << 20;
constexpr uint64_t max_payload_bytes = 256u << 20;
constexpr uint64_t max_archive_bytes = max_payload_bytes + max_manifest_bytes + (max_members + 2) * 1024 + 10240;
constexpr size_t arena_bytes = 8u << 20;
struct error { const char* message; };
inline const char* last_error = "invalid package";
inline jmp_buf* error_target = nullptr;
inline void require(bool value, const char* message) { if (!value) { last_error=message; if(error_target)longjmp(*error_target,1); } }

class sha256 {
    uint32_t state_[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                           0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    uint64_t bytes_ = 0;
    uint8_t block_[64]{};
    size_t used_ = 0;
    static uint32_t rotate(uint32_t value, unsigned count) { return (value >> count) | (value << (32-count)); }
    void transform(const uint8_t* input) {
        static constexpr uint32_t k[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for (unsigned i=0;i<16;++i) w[i]=(uint32_t(input[i*4])<<24)|(uint32_t(input[i*4+1])<<16)|(uint32_t(input[i*4+2])<<8)|input[i*4+3];
        for (unsigned i=16;i<64;++i) { uint32_t a=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3); uint32_t b=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10); w[i]=w[i-16]+a+w[i-7]+b; }
        uint32_t a=state_[0],b=state_[1],c=state_[2],d=state_[3],e=state_[4],f=state_[5],g=state_[6],h=state_[7];
        for (unsigned i=0;i<64;++i) { uint32_t s1=rotate(e,6)^rotate(e,11)^rotate(e,25), ch=(e&f)^(~e&g); uint32_t t1=h+s1+ch+k[i]+w[i]; uint32_t s0=rotate(a,2)^rotate(a,13)^rotate(a,22), maj=(a&b)^(a&c)^(b&c); uint32_t t2=s0+maj; h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2; }
        state_[0]+=a;state_[1]+=b;state_[2]+=c;state_[3]+=d;state_[4]+=e;state_[5]+=f;state_[6]+=g;state_[7]+=h;
    }
public:
    void update(const void* source, size_t length) {
        const auto* input=static_cast<const uint8_t*>(source); bytes_+=length;
        while (length) { size_t n=64-used_; if(n>length)n=length; std::memcpy(block_+used_,input,n);used_+=n;input+=n;length-=n;if(used_==64){transform(block_);used_=0;} }
    }
    void finish(uint8_t output[32]) {
        const uint64_t bits=bytes_*8; block_[used_++]=0x80;
        if(used_>56){while(used_<64)block_[used_++]=0;transform(block_);used_=0;}
        while(used_<56)block_[used_++]=0;
        for(unsigned i=0;i<8;++i)block_[63-i]=uint8_t(bits>>(i*8));transform(block_);
        for(unsigned i=0;i<8;++i){output[i*4]=uint8_t(state_[i]>>24);output[i*4+1]=uint8_t(state_[i]>>16);output[i*4+2]=uint8_t(state_[i]>>8);output[i*4+3]=uint8_t(state_[i]);}
    }
};
inline void hex_digest(const uint8_t digest[32], char output[65]) {
    static constexpr char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;++i){output[i*2]=hex[digest[i]>>4];output[i*2+1]=hex[digest[i]&15];}output[64]=0;
}
inline bool hash_text(const char* value) {
    if(std::strlen(value)!=64)return false;
    for(unsigned i=0;i<64;++i)if(!((value[i]>='0'&&value[i]<='9')||(value[i]>='a'&&value[i]<='f')))return false;
    return true;
}

enum class kind : uint8_t { object, array, string, number, boolean, null_value };
struct value { kind type; value* next; value* child; char* key; char* text; size_t length; int64_t number; uint64_t payload_offset; bool boolean; bool seen; };
inline unsigned char* json_arena[2]{};
inline bool ensure_json_arena(unsigned index){if(index>=2)return false;if(!json_arena[index])json_arena[index]=static_cast<unsigned char*>(std::malloc(arena_bytes));return json_arena[index]!=nullptr;}
class json_parser {
    const char* input_; size_t length_; size_t at_=0; size_t nodes_=0; size_t arena_used_=0; unsigned arena_index_;
    void ws(){while(at_<length_&&(input_[at_]==' '||input_[at_]=='\n'||input_[at_]=='\r'||input_[at_]=='\t'))++at_;}
    void* allocate(size_t n){require(n<=arena_bytes-arena_used_&&ensure_json_arena(arena_index_),"JSON metadata exceeds memory budget");void* p=json_arena[arena_index_]+arena_used_;arena_used_+=n;return p;}
    value* node(kind type){require(++nodes_<=100000,"too many JSON values");size_t padding=(alignof(value)-arena_used_%alignof(value))%alignof(value);if(padding)allocate(padding);auto* p=static_cast<value*>(allocate(sizeof(value)));std::memset(p,0,sizeof(*p));p->type=type;return p;}
    static int hex(char c){if(c>='0'&&c<='9')return c-'0';if(c>='a'&&c<='f')return c-'a'+10;if(c>='A'&&c<='F')return c-'A'+10;return -1;}
    uint32_t unicode(){require(at_+4<=length_,"truncated JSON escape");uint32_t cp=0;for(unsigned i=0;i<4;++i){int h=hex(input_[at_++]);require(h>=0,"invalid JSON escape");cp=(cp<<4)|unsigned(h);}return cp;}
    char* string(size_t& out_length){require(at_<length_&&input_[at_++]=='"',"expected JSON string");size_t scan=at_;bool closed=false;while(scan<length_){char c=input_[scan++];if(c=='"'){closed=true;break;}if(c=='\\'){if(scan<length_){char e=input_[scan++];if(e=='u'){require(scan+4<=length_,"truncated JSON escape");scan+=4;}}}}require(closed,"unterminated JSON string");char* out=static_cast<char*>(allocate(scan-at_+1));size_t used=0;
        while(at_<length_){unsigned char c=input_[at_++];if(c=='"'){out[used]=0;out_length=used;require(xos::text::valid(out,static_cast<xos::u32>(used)),"invalid UTF-8 JSON string");return out;}require(c>=0x20,"control byte in JSON string");
            if(c!='\\'){out[used++]=char(c);continue;}require(at_<length_,"truncated JSON escape");char e=input_[at_++];if(e=='"'||e=='\\'||e=='/')out[used++]=e;else if(e=='b')out[used++]='\b';else if(e=='f')out[used++]='\f';else if(e=='n')out[used++]='\n';else if(e=='r')out[used++]='\r';else if(e=='t')out[used++]='\t';else if(e=='u'){
                uint32_t cp=unicode();if(cp>=0xd800&&cp<=0xdbff){require(at_+2<=length_&&input_[at_++]=='\\'&&input_[at_++]=='u',"invalid JSON surrogate");uint32_t low=unicode();require(low>=0xdc00&&low<=0xdfff,"invalid JSON surrogate");cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);}else require(cp<0xdc00||cp>0xdfff,"invalid JSON surrogate");
                require(cp!=0,"NUL in JSON string");if(cp<0x80)out[used++]=char(cp);else if(cp<0x800){out[used++]=char(0xc0|(cp>>6));out[used++]=char(0x80|(cp&63));}else if(cp<0x10000){out[used++]=char(0xe0|(cp>>12));out[used++]=char(0x80|((cp>>6)&63));out[used++]=char(0x80|(cp&63));}else{out[used++]=char(0xf0|(cp>>18));out[used++]=char(0x80|((cp>>12)&63));out[used++]=char(0x80|((cp>>6)&63));out[used++]=char(0x80|(cp&63));}
            }else{require(false,"invalid JSON escape");return nullptr;}
        }require(false,"unterminated JSON string");return nullptr;}
    value* parse_value(unsigned depth){require(depth<=8,"JSON nesting exceeds 8");ws();require(at_<length_,"truncated JSON");char c=input_[at_];
        if(c=='{'){++at_;value* out=node(kind::object);value** tail=&out->child;ws();if(at_<length_&&input_[at_]=='}'){++at_;return out;}for(;;){ws();size_t kl=0;char* key=string(kl);for(value* p=out->child;p;p=p->next)require(std::strcmp(p->key,key)!=0,"duplicate JSON key");ws();require(at_<length_&&input_[at_++]==':',"expected JSON colon");value* item=parse_value(depth+1);item->key=key;*tail=item;tail=&item->next;ws();require(at_<length_,"truncated JSON object");char sep=input_[at_++];if(sep=='}')break;require(sep==',',"expected JSON comma");}return out;}
        if(c=='['){++at_;value* out=node(kind::array);value** tail=&out->child;ws();if(at_<length_&&input_[at_]==']'){++at_;return out;}for(;;){value* item=parse_value(depth+1);*tail=item;tail=&item->next;ws();require(at_<length_,"truncated JSON array");char sep=input_[at_++];if(sep==']')break;require(sep==',',"expected JSON comma");}return out;}
        if(c=='"'){value* out=node(kind::string);out->text=string(out->length);return out;}
        if(c=='-'||(c>='0'&&c<='9')){size_t start=at_;if(input_[at_]=='-')++at_;require(at_<length_,"invalid JSON integer");if(input_[at_]=='0')++at_;else{require(input_[at_]>='1'&&input_[at_]<='9',"invalid JSON integer");while(at_<length_&&input_[at_]>='0'&&input_[at_]<='9')++at_;}require(at_==length_||(input_[at_]!='.'&&input_[at_]!='e'&&input_[at_]!='E'),"non-integer JSON number");value* out=node(kind::number);bool neg=input_[start]=='-';size_t i=start+(neg?1:0);uint64_t n=0;for(;i<at_;++i){unsigned d=unsigned(input_[i]-'0');require(n<=(uint64_t(INT64_MAX)-d)/10,"JSON integer overflow");n=n*10+d;}require(!neg||n<=uint64_t(INT64_MAX)+1,"JSON integer overflow");out->number=neg?(n==uint64_t(INT64_MAX)+1?INT64_MIN:-int64_t(n)):int64_t(n);return out;}
        const char* literals[]={"true","false","null"};kind types[]={kind::boolean,kind::boolean,kind::null_value};for(unsigned i=0;i<3;++i){size_t n=std::strlen(literals[i]);if(at_+n<=length_&&!std::memcmp(input_+at_,literals[i],n)){at_+=n;value* out=node(types[i]);out->boolean=i==0;return out;}}require(false,"invalid JSON value");return nullptr;}
public:
    json_parser(const char* input,size_t length,unsigned arena_index=0):input_(input),length_(length),arena_index_(arena_index){require(arena_index<2,"invalid parser arena");}
    value* parse(){require(length_<=max_manifest_bytes,"JSON exceeds 1 MiB");require(ensure_json_arena(arena_index_),"cannot reserve JSON metadata memory");std::memset(json_arena[arena_index_],0,arena_bytes);value* out=parse_value(0);ws();require(at_==length_,"trailing bytes after JSON");return out;}
};
inline value* field(value* object,const char* name){if(!object||object->type!=kind::object)return nullptr;for(value* p=object->child;p;p=p->next)if(p->key&&std::strcmp(p->key,name)==0)return p;return nullptr;}
inline bool identifier(const char* p){size_t n=std::strlen(p);if(!n||n>80||p[0]<'a'||p[0]>'z')return false;bool after_separator=false;for(size_t i=1;i<n;++i){char c=p[i];if(c=='.'||c=='-'){if(after_separator||i+1==n)return false;after_separator=true;continue;}if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'))return false;after_separator=false;}return !after_separator;}
inline bool package_path(const char* p){size_t n=std::strlen(p);if(!n||n>255||p[0]=='/'||p[n-1]=='/')return false;char part[101];size_t used=0,segments=0;for(size_t i=0;i<=n;++i){char c=p[i];if(c=='/'||c==0){if(!used||used>100)return false;part[used]=0;size_t plen=std::strlen(part);if(!std::strcmp(part,".")||!std::strcmp(part,"..")||part[used-1]=='.'||part[used-1]==' ')return false;if(plen>=7&&(part[0]=='X'||part[0]=='x')&&(part[1]=='O'||part[1]=='o')&&(part[2]=='S'||part[2]=='s')){const char* suffix=part+plen-4;if((suffix[0]=='.')&&(suffix[1]=='T'||suffix[1]=='t')&&(suffix[2]=='M'||suffix[2]=='m')&&(suffix[3]=='P'||suffix[3]=='p'))return false;}if(++segments==1&&std::strcmp(part,"usr"))return false;if(segments==2&&std::strcmp(part,"bin")&&std::strcmp(part,"lib")&&std::strcmp(part,"share"))return false;used=0;continue;}if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='.'||c=='+'||c=='-'))return false;if(used<100)part[used++]=c;else return false;}if(segments<3||(std::strncmp(p,"usr/bin/",8)==0&&std::strchr(p+8,'/')))return false;size_t archive_length=n+8;if(archive_length<=100)return true;for(size_t i=8;i<archive_length;++i)if(p[i-8]=='/'&&i<=155&&archive_length-i-1<=100)return true;return false;}
inline bool directory_path(const char* p){size_t n=std::strlen(p);if(!n||n>255||p[0]=='/'||p[n-1]=='/')return false;char part[101];size_t used=0,segments=0;for(size_t i=0;i<=n;++i){char c=p[i];if(c=='/'||c==0){if(!used||used>100)return false;part[used]=0;size_t len=std::strlen(part);if(!std::strcmp(part,".")||!std::strcmp(part,"..")||part[len-1]=='.'||part[len-1]==' ')return false;for(size_t j=0;j<len;++j)if(!((part[j]>='A'&&part[j]<='Z')||(part[j]>='a'&&part[j]<='z')||(part[j]>='0'&&part[j]<='9')||part[j]=='_'||part[j]=='.'||part[j]=='+'||part[j]=='-'))return false;if(++segments==1&&std::strcmp(part,"usr"))return false;if(segments==2&&std::strcmp(part,"bin")&&std::strcmp(part,"lib")&&std::strcmp(part,"share"))return false;used=0;continue;}if(used>=100)return false;part[used++]=c;}return segments>=1;}
inline bool octal(const uint8_t* p,size_t n,uint64_t& value){if(p[0]&0x80)return false;size_t i=0;while(i<n&&p[i]==' ')++i;value=0;bool any=false;for(;i<n&&p[i]&&p[i]!=' ';++i){if(p[i]<'0'||p[i]>'7'||value>(UINT64_MAX-(p[i]-'0'))/8)return false;value=value*8+(p[i]-'0');any=true;}for(;i<n;++i)if(p[i]&&p[i]!=' ')return false;if(!any)value=0;return true;}
inline char* tar_string(const uint8_t* p,size_t n,char* out){size_t len=0;while(len<n&&p[len])++len;for(size_t i=len;i<n;++i)if(p[i])return nullptr;for(size_t i=0;i<len;++i){if(p[i]<0x20||p[i]>0x7e)return nullptr;out[i]=char(p[i]);}out[len]=0;return out;}
inline uint16_t elf_u16(const uint8_t* p){return uint16_t(p[0])|(uint16_t(p[1])<<8);}
inline uint32_t elf_u32(const uint8_t* p){return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);}
inline uint64_t elf_u64(const uint8_t* p){return uint64_t(elf_u32(p))|(uint64_t(elf_u32(p+4))<<32);}
inline bool elf_read_at(FILE* file,uint64_t base,uint64_t file_size,uint64_t offset,void* output,size_t length){
    if(offset>file_size||length>file_size-offset||base>uint64_t(LONG_MAX)-offset)return false;
    if(std::fseek(file,static_cast<long>(base+offset),SEEK_SET)!=0)return false;
    return std::fread(output,1,length,file)==length;
}
inline void validate_executable_elf(FILE* file,uint64_t base,uint64_t file_size){
    uint8_t header[64];require(file_size>=sizeof(header)&&elf_read_at(file,base,file_size,0,header,sizeof(header)),"truncated executable ELF header");
    require(!std::memcmp(header,"\x7f""ELF\x02\x01\x01",7),"executable is not ELF64 little-endian v1");
    uint16_t type=elf_u16(header+16),machine=elf_u16(header+18),ehsize=elf_u16(header+52),phsize=elf_u16(header+54),phcount=elf_u16(header+56);
    uint32_t version=elf_u32(header+20),flags=elf_u32(header+48);uint64_t entry=elf_u64(header+24),phoff=elf_u64(header+32);
    require(type==2&&machine==62&&version==1&&(header[7]==0||header[7]==3)&&header[8]==0&&flags==0,"unsupported executable ELF target/type");
    require(ehsize==64&&phsize==56&&phcount>0&&phcount<=32&&phoff>=64&&phoff<=file_size&&uint64_t(phcount)*56<=file_size-phoff,"invalid executable program headers");
    uint8_t ph[32*56];require(elf_read_at(file,base,file_size,phoff,ph,size_t(phcount)*56),"truncated executable program headers");
    struct load_range{uint64_t first,last;};load_range loads[8]{};size_t load_count=0;bool entry_ok=false,tls_seen=false,tls_has_bytes=false;uint64_t tls_off=0,tls_addr=0,tls_len=0;uint64_t load_file_off[8]{},load_file_addr[8]{},load_file_len[8]{};uint64_t pages=36;
    constexpr uint64_t page=4096,image_begin=0x40000000,image_end=0x7ffdb000;
    for(unsigned i=0;i<phcount;++i){const uint8_t* p=ph+i*56;uint32_t kind=elf_u32(p),access=elf_u32(p+4);uint64_t offset=elf_u64(p+8),address=elf_u64(p+16),filesz=elf_u64(p+32),memsz=elf_u64(p+40),align=elf_u64(p+48);
        if(kind==7){if(filesz==0&&memsz==0)continue;require(!tls_seen&&(access==4||access==6),"invalid executable TLS segment");tls_seen=true;tls_off=offset;tls_addr=address;tls_len=filesz;require(filesz<=memsz&&memsz<=0x100000&&offset<=file_size&&filesz<=file_size-offset&&address>=image_begin&&address<image_end&&memsz<=image_end-address,"executable TLS bounds invalid");if(!align)align=1;require(align<=65536&&(align&(align-1))==0&&address%align==0&&offset%align==0,"executable TLS alignment invalid");continue;}
        if(kind!=1){require(kind==0||kind==4||kind==6||kind==0x6474e552||(kind==0x6474e551&&(access&1)==0),"dynamic/unsupported executable ELF segment");continue;}
        if(filesz==0&&memsz==0)continue;
        require(filesz<=memsz&&offset<=file_size&&filesz<=file_size-offset,"executable LOAD file bounds invalid");require((access==4||access==5||access==6)&&address>=image_begin&&address<image_end&&memsz<=image_end-address,"executable LOAD permissions/address invalid");
        require(align<=1||((align&(align-1))==0&&address%align==offset%align),"executable LOAD alignment invalid");
        require(address%page==offset%page,"executable LOAD page congruence mismatch");
        uint64_t first=address&~(page-1);require(memsz<=UINT64_MAX-address&&address+memsz<=UINT64_MAX-(page-1),"executable LOAD address overflow");uint64_t last=(address+memsz+page-1)&~(page-1);
        require(last<=0x5fe00000||first>=0x70000000,"executable LOAD overlaps TLS/heap arena");
        require(load_count<8,"too many executable LOAD segments");for(size_t j=0;j<load_count;++j)require(!(first<loads[j].last&&loads[j].first<last),"overlapping executable LOAD pages");
        loads[load_count]={first,last};load_file_off[load_count]=offset;load_file_addr[load_count]=address;load_file_len[load_count]=filesz;++load_count;pages+=(last-first)/page;entry_ok|=(access&1)&&entry>=address&&entry-address<filesz;
    }
    if(tls_seen&&tls_len){for(size_t i=0;i<load_count;++i)if(tls_off>=load_file_off[i]&&tls_off-load_file_off[i]<=load_file_len[i]&&tls_len<=load_file_len[i]-(tls_off-load_file_off[i])&&tls_addr>=load_file_addr[i]&&tls_addr-load_file_addr[i]==tls_off-load_file_off[i])tls_has_bytes=true;require(tls_has_bytes,"executable TLS template is outside LOAD bytes");}
    require(load_count>0&&entry_ok&&pages<=65536,"invalid executable entry/LOAD count/page budget");
}

inline void exact_fields(value* object,const char* const* names,size_t count){require(object&&object->type==kind::object,"expected JSON object");size_t found=0;for(value* p=object->child;p;p=p->next){bool known=false;for(size_t i=0;i<count;++i)if(!std::strcmp(p->key,names[i]))known=true;require(known,"unknown JSON field");++found;}require(found==count,"missing JSON field");}
inline value* need(value* object,const char* name,kind type){value* p=field(object,name);require(p&&p->type==type,"missing or invalid JSON field");return p;}
inline const char* text(value* p,const char* label,size_t max=1024){require(p&&p->type==kind::string&&p->length>0,"invalid string field");size_t characters=0;for(size_t i=0;i<p->length;++i){unsigned char c=static_cast<unsigned char>(p->text[i]);require(c!=0,"NUL in string field");if((c&0xc0)!=0x80)++characters;}require(characters<=max,"invalid string field");(void)label;return p->text;}
inline uint64_t unsigned_number(value* p,uint64_t max,const char* message){require(p&&p->type==kind::number&&p->number>=0&&uint64_t(p->number)<=max,message);return uint64_t(p->number);}
inline bool ascii_equal_fold(const char* a,const char* b){while(*a&&*b){char x=*a++,y=*b++;if(x>='A'&&x<='Z')x=char(x+32);if(y>='A'&&y<='Z')y=char(y+32);if(x!=y)return false;}return *a==*b;}
inline int compare_fold(const char* a,const char* b){for(;;){char x=*a++,y=*b++;if(x>='A'&&x<='Z')x=char(x+32);if(y>='A'&&y<='Z')y=char(y+32);if(x!=y)return static_cast<unsigned char>(x)<static_cast<unsigned char>(y)?-1:1;if(!x)return 0;}}
inline bool path_prefix(const char* parent,const char* child){size_t n=std::strlen(parent);if(std::strlen(child)<=n||child[n]!='/')return false;for(size_t i=0;i<n;++i){char a=parent[i],b=child[i];if(a>='A'&&a<='Z')a=char(a+32);if(b>='A'&&b<='Z')b=char(b+32);if(a!=b)return false;}return true;}
inline value* manifest_file_sort[max_members];
inline value* manifest_license_sort[max_members];
inline int compare_file_node(const void* a,const void* b){return compare_fold(field(*static_cast<value* const*>(a),"path")->text,field(*static_cast<value* const*>(b),"path")->text);}
inline int compare_license_node(const void* a,const void* b){return compare_fold((*static_cast<value* const*>(a))->text,(*static_cast<value* const*>(b))->text);}
inline value* find_manifest_file(value** files,size_t count,const char* path){size_t low=0,high=count;while(low<high){size_t mid=low+(high-low)/2;int cmp=compare_fold(field(files[mid],"path")->text,path);if(cmp<0)low=mid+1;else high=mid;}return low<count&&ascii_equal_fold(field(files[low],"path")->text,path)?files[low]:nullptr;}
inline void validate_manifest(value* manifest){
    static const char* const top[]={"format_version","id","upstream_version","revision","target_profile","required_features","runtime_dependencies","files","licenses","build_receipt","source"};
    exact_fields(manifest,top,11);require(unsigned_number(field(manifest,"format_version"),1,"unsupported XPK version")==1,"unsupported XPK version");
    const char* id=text(need(manifest,"id",kind::string),"id",80);require(identifier(id),"invalid package id");
    const char* profile=text(need(manifest,"target_profile",kind::string),"target profile",80);require(identifier(profile),"invalid target profile");
#ifdef XYP_PACKAGE_PROFILE_ID
    require(std::strcmp(profile,XYP_PACKAGE_PROFILE_ID)==0,"package target profile differs from this xypm build");
#endif
    text(need(manifest,"upstream_version",kind::string),"version",1024);text(need(manifest,"source",kind::string),"source",1024);
    unsigned_number(field(manifest,"revision"),0x7fffffff,"invalid revision");
    value* features=need(manifest,"required_features",kind::array);size_t feature_count=0;
    for(value* p=features->child;p;p=p->next){require(++feature_count<=64&&p->type==kind::string&&identifier(p->text),"invalid feature");for(value* q=features->child;q!=p;q=q->next)require(std::strcmp(q->text,p->text)!=0,"duplicate feature");
#ifdef XYP_PACKAGE_FEATURES
        require(XYP_PACKAGE_FEATURES(p->text),"required feature unavailable in this xypm profile");
#endif
    }
    value* deps=need(manifest,"runtime_dependencies",kind::array);size_t dep_count=0;
    for(value* p=deps->child;p;p=p->next){require(++dep_count<=128,"too many runtime dependencies");static const char* const dep_fields[]={"id","upstream_version","revision","sha256"};exact_fields(p,dep_fields,4);const char* dep_id=text(need(p,"id",kind::string),"dependency id",80);require(identifier(dep_id)&&std::strcmp(dep_id,id)!=0,"invalid/self dependency");text(need(p,"upstream_version",kind::string),"dependency version",1024);unsigned_number(field(p,"revision"),0x7fffffff,"invalid dependency revision");require(hash_text(text(need(p,"sha256",kind::string),"dependency hash",64)),"invalid dependency hash");for(value* q=deps->child;q!=p;q=q->next)require(std::strcmp(field(q,"id")->text,dep_id)!=0,"duplicate dependency");}
    value* files=need(manifest,"files",kind::array);size_t file_count=0;uint64_t total=0;
    for(value* p=files->child;p;p=p->next){require(++file_count<=max_members,"too many package files");static const char* const file_fields[]={"path","type","size","sha256","role"};exact_fields(p,file_fields,5);const char* path=text(need(p,"path",kind::string),"file path",255);require(package_path(path),"invalid package destination");require(std::strcmp(text(need(p,"type",kind::string),"file type",8),"file")==0,"unsupported payload type");value* sz=field(p,"size");uint64_t size=unsigned_number(sz,max_file_bytes,"package file exceeds size limit");require(total<=max_payload_bytes-size,"package payload exceeds limit");total+=size;require(hash_text(text(need(p,"sha256",kind::string),"file hash",64)),"invalid payload hash");const char* role=text(need(p,"role",kind::string),"file role",16);require(!std::strcmp(role,"data")||!std::strcmp(role,"executable"),"invalid file role");p->seen=false;manifest_file_sort[file_count-1]=p;
    }
    require(file_count>0,"empty package file list");
    std::qsort(manifest_file_sort,file_count,sizeof(manifest_file_sort[0]),compare_file_node);
    for(size_t i=0;i<file_count;++i){const char* path=field(manifest_file_sort[i],"path")->text;if(i)require(!ascii_equal_fold(field(manifest_file_sort[i-1],"path")->text,path),"duplicate/case-folded package path");char prefix[256];size_t n=std::strlen(path);for(size_t j=0;j<n;++j)if(path[j]=='/'){std::memcpy(prefix,path,j);prefix[j]=0;require(find_manifest_file(manifest_file_sort,file_count,prefix)==nullptr,"package file/directory collision");}}
    value* licenses=need(manifest,"licenses",kind::array);size_t license_count=0;
    for(value* p=licenses->child;p;p=p->next){require(++license_count<=max_members&&p->type==kind::string&&package_path(p->text),"invalid license list");manifest_license_sort[license_count-1]=p;}
    require(license_count>0,"package license materials required");
    std::qsort(manifest_license_sort,license_count,sizeof(manifest_license_sort[0]),compare_license_node);for(size_t i=0;i<license_count;++i){value* p=manifest_license_sort[i];if(i)require(!ascii_equal_fold(manifest_license_sort[i-1]->text,p->text),"duplicate license path");value* found=find_manifest_file(manifest_file_sort,file_count,p->text);require(found&&std::strcmp(field(found,"path")->text,p->text)==0&&std::strcmp(field(found,"role")->text,"data")==0,"license file missing from payload");}
    value* receipt=need(manifest,"build_receipt",kind::object);static const char* const receipt_fields[]={"path","sha256"};exact_fields(receipt,receipt_fields,2);const char* receipt_path=text(need(receipt,"path",kind::string),"receipt path",255);require(package_path(receipt_path),"invalid receipt path");const char* receipt_hash=text(need(receipt,"sha256",kind::string),"receipt hash",64);require(hash_text(receipt_hash),"invalid receipt hash");value* receipt_file=find_manifest_file(manifest_file_sort,file_count,receipt_path);require(receipt_file&&std::strcmp(field(receipt_file,"path")->text,receipt_path)==0&&std::strcmp(field(receipt_file,"sha256")->text,receipt_hash)==0&&std::strcmp(field(receipt_file,"role")->text,"data")==0,"receipt binding mismatch");
}
struct verified_package { value* manifest; char digest[65]; uint32_t files; };
inline bool read_exact(FILE* file,void* out,size_t count,sha256& hash){size_t got=std::fread(out,1,count,file);if(got)hash.update(out,got);return got==count;}
inline verified_package verify_package(FILE* file,uint64_t archive_size){
    require(file&&archive_size<=max_archive_bytes&&archive_size%512==0,"package size/alignment invalid");require(std::fseek(file,0,SEEK_SET)==0,"cannot rewind package");sha256 package_hash;uint64_t consumed=0;value* manifest=nullptr;uint32_t member_count=0,payload_count=0;uint8_t header[512],buffer[32768];
    static const uint8_t zero_block[512]={};
    for(;;){require(read_exact(file,header,512,package_hash),"truncated tar header");consumed+=512;if(!std::memcmp(header,zero_block,512)){require(read_exact(file,header,512,package_hash)&&!std::memcmp(header,zero_block,512),"missing tar end markers");consumed+=512;while(consumed<archive_size){size_t n=archive_size-consumed>sizeof(buffer)?sizeof(buffer):size_t(archive_size-consumed);require(read_exact(file,buffer,n,package_hash),"truncated package tail");for(size_t i=0;i<n;++i)require(buffer[i]==0,"nonzero tar tail");consumed+=n;}break;}
        require(member_count<=max_members,"too many tar members");++member_count;require(!std::memcmp(header+257,"ustar\0",6)&&!std::memcmp(header+263,"00",2),"only POSIX ustar is supported");uint64_t stored=0,size=0;require(octal(header+148,8,stored),"invalid tar checksum field");uint64_t sum=0;for(unsigned i=0;i<512;++i)sum+=i>=148&&i<156?32:header[i];require(sum==stored,"tar checksum mismatch");require(header[156]==0||header[156]=='0',"only regular tar files are supported");for(unsigned i=157;i<257;++i)require(header[i]==0,"tar link/extension field is not empty");for(unsigned i=500;i<512;++i)require(header[i]==0,"nonzero tar header padding");char name[101],prefix[156],full[257];require(tar_string(header,100,name)&&tar_string(header+345,155,prefix),"invalid tar path");if(prefix[0]){int n=std::snprintf(full,sizeof(full),"%s/%s",prefix,name);require(n>0&&size_t(n)<sizeof(full),"tar path too long");}else{require(std::strlen(name)<sizeof(full),"tar path too long");std::strcpy(full,name);}require(octal(header+124,12,size),"invalid tar member size");
        if(member_count==1){require(!std::strcmp(full,"manifest.json")&&size<=max_manifest_bytes,"bounded manifest.json must be first");char* data=static_cast<char*>(std::malloc(size?size:1));require(data!=nullptr,"out of memory reading manifest");require(read_exact(file,data,size,package_hash),"truncated manifest");consumed+=size;json_parser parser(data,size);manifest=parser.parse();validate_manifest(manifest);std::free(data);
        }else{require(manifest!=nullptr,"payload before manifest");value* found=nullptr;for(value* p=field(manifest,"files")->child;p;p=p->next){char expected[264];int n=std::snprintf(expected,sizeof(expected),"payload/%s",field(p,"path")->text);require(n>0&&size_t(n)<sizeof(expected),"package member name too long");if(!std::strcmp(expected,full)){found=p;break;}}require(found&&!found->seen,"unexpected or duplicate payload member");require(size==uint64_t(field(found,"size")->number),"payload length mismatch");sha256 member_hash;uint64_t remaining=size;uint64_t payload_start=consumed;found->payload_offset=payload_start;
            while(remaining){size_t n=remaining>sizeof(buffer)?sizeof(buffer):size_t(remaining);require(read_exact(file,buffer,n,package_hash),"truncated payload member");member_hash.update(buffer,n);remaining-=n;consumed+=n;}uint8_t digest[32];char text_hash[65];member_hash.finish(digest);hex_digest(digest,text_hash);require(std::strcmp(text_hash,field(found,"sha256")->text)==0,"payload hash mismatch");if(std::strcmp(field(found,"role")->text,"executable")==0){validate_executable_elf(file,payload_start,size);require(std::fseek(file,static_cast<long>(consumed),SEEK_SET)==0,"cannot resume package validation");}found->seen=true;++payload_count;
        }
        uint64_t padding=(512-(size%512))%512;if(padding){require(read_exact(file,buffer,size_t(padding),package_hash),"truncated tar padding");consumed+=padding;for(size_t i=0;i<padding;++i)require(buffer[i]==0,"nonzero tar member padding");}
        require(consumed<=archive_size,"package length overflow");
    }
    require(manifest!=nullptr,"missing package manifest");uint32_t expected=0;for(value* p=field(manifest,"files")->child;p;p=p->next){require(p->seen,"missing payload file");++expected;}require(payload_count==expected,"incomplete payload");uint8_t digest[32];char text_hash[65];package_hash.finish(digest);hex_digest(digest,text_hash);verified_package result{};result.manifest=manifest;std::memcpy(result.digest,text_hash,sizeof(text_hash));result.files=payload_count;return result;
}
}
