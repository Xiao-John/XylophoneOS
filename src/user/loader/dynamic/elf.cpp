// SPDX-License-Identifier: Apache-2.0
#include <xos/dynamic_elf.hpp>

namespace xos::dynamic {
namespace {
u64 value(const u8* p, u32 n) { u64 r=0; for (u32 i=0;i<n;++i) r|=u64{p[i]}<<(8*i); return r; }
bool range(u64 a,u64 n,u64 size) { return a<=size && n<=size-a; }
bool power(u64 n) { return n && !(n&(n-1)); }
bool same(const char* a,const char* b) { for (u32 i=0;i<128;++i) { if(a[i]!=b[i])return false; if(!a[i])return true; } return false; }
u32 elf_hash(const char* name) { u32 h=0; for(u32 i=0;name[i];++i) { h=(h<<4)+static_cast<u8>(name[i]); const u32 g=h&0xf0000000; if(g)h^=g>>24; h&=~g; } return h; }
struct reader {
    elf::read_exact_fn read; void* context; u64 size; elf_image& image;
    bool file(u64 a,void* p,u32 n) { return range(a,n,size) && read(context,a,static_cast<u8*>(p),n); }
    const elf::segment* segment(u64 a,u64 n,u32 rights,bool file_backed=true) const {
        for(u32 i=0;i<image.load_count;++i) { const auto& l=image.loads[i];
            if((l.permissions&rights)==rights && a>=l.address && range(a-l.address,n,file_backed?l.file_bytes:l.memory_bytes)) return &l; }
        return nullptr;
    }
    bool memory(u64 a,void* p,u32 n) { const auto* l=segment(a,n,map_read); return l && file(l->offset+a-l->address,p,n); }
    bool mapped(u64 a,u64 n,u32 rights) const { return segment(a,n,rights,false)!=nullptr; }
    bool string(u64 table,u64 bytes,u64 index,char (&out)[128]) {
        if(index>=bytes)return false;
        const u32 amount=bytes-index<sizeof(out)?static_cast<u32>(bytes-index):sizeof(out);
        if(!memory(table+index,out,amount))return false;
        for(u32 i=0;i<amount;++i) {
            if(!out[i]) { for(u32 j=i+1;j<sizeof(out);++j)out[j]=0;return true; }
            if(static_cast<u8>(out[i])<0x20 || static_cast<u8>(out[i])==0x7f)return false;
        } return false;
    }
};
struct dynamic_info {
    u64 strings=0,string_bytes=0,symbols=0,symbol_size=0,hash=0,gnu_hash=0;
    u64 rela=0,rela_bytes=0,rela_size=0,jmp=0,jmp_bytes=0,plt_rel=0;
    u64 relr=0,relr_bytes=0,relr_size=0,versions=0,defs=0,def_count=0,needs=0,need_count=0;
    u64 init=0,fini=0,init_array=0,init_bytes=0,fini_array=0,fini_bytes=0,preinit=0,preinit_bytes=0;
    u64 flags=0,flags1=0,soname=0,relacount=0;
    bool has_soname=false,now=false;
};
bool add_version(reader& r,u32 hash,u16 idx,u16 flags,bool definition,const char* name,const char* provider) {
    if(!idx || idx>0x7fff || (flags&~3u) || r.image.version_count==elf_version_limit || elf_hash(name)!=hash)return false;
    for(u32 i=0;i<r.image.version_count;++i)if(r.image.versions[i].index==idx)return false;
    auto& v=r.image.versions[r.image.version_count++];v.hash=hash;v.index=idx;v.flags=flags;v.definition=definition;
    for(u32 i=0;i<128;++i){v.name[i]=name[i];v.provider[i]=provider[i];}return true;
}
bool version_tables(reader& r,const dynamic_info& d,const generation& g,u32 index) {
    if((d.defs==0)!=(d.def_count==0) || (d.needs==0)!=(d.need_count==0)
       || d.def_count>elf_version_limit || d.need_count>generation_max_objects)return false;
    u64 at=d.defs;
    for(u32 i=0;i<d.def_count;++i) {
        u8 data[20];if(!r.memory(at,data,sizeof(data)))return false;
        const u32 count=static_cast<u32>(value(data+6,2));const u64 aux=value(data+12,4),next=value(data+16,4);
        if(value(data,2)!=1 || !count || count>elf_version_limit || aux<sizeof(data) || aux%4 || !range(at,aux,~u64{0}))return false;
        u64 a=at+aux;char first[128]{},empty[128]{};
        for(u32 j=0;j<count;++j) { u8 entry[8];char name[128]{};
            if(!r.memory(a,entry,8) || !r.string(d.strings,d.string_bytes,value(entry,4),name) || !name[0])return false;
            if(j==0)for(u32 k=0;k<128;++k)first[k]=name[k];
            const u64 step=value(entry+4,4);if((j+1==count)!=(step==0) || (step && (step<8 || step%4 || !range(a,step,~u64{0}))))return false;
            a+=step;
        }
        if(!add_version(r,static_cast<u32>(value(data+8,4)),static_cast<u16>(value(data+4,2)),static_cast<u16>(value(data+2,2)),true,first,empty))return false;
        if((i+1==d.def_count)!=(next==0) || (next && (next<20 || next%4 || !range(at,next,~u64{0}))))return false;
        at+=next;
    }
    at=d.needs;
    for(u32 i=0;i<d.need_count;++i) {
        u8 data[16];char provider[128]{};
        if(!r.memory(at,data,16) || value(data,2)!=1 || !r.string(d.strings,d.string_bytes,value(data+4,4),provider))return false;
        bool dependency=false;const auto& object=g.objects[index];
        for(u32 j=0;j<object.needed_count;++j)dependency=dependency || same(provider,g.objects[object.needed[j]].soname);
        const u32 count=static_cast<u32>(value(data+2,2));const u64 aux=value(data+8,4),next=value(data+12,4);
        if(!dependency || !count || count>elf_version_limit || aux<16 || aux%4 || !range(at,aux,~u64{0}))return false;
        u64 a=at+aux;
        for(u32 j=0;j<count;++j) {
            u8 entry[16];char name[128]{};
            if(!r.memory(a,entry,16) || !r.string(d.strings,d.string_bytes,value(entry+8,4),name) || !name[0]
              || !add_version(r,static_cast<u32>(value(entry,4)),static_cast<u16>(value(entry+6,2)),static_cast<u16>(value(entry+4,2)),false,name,provider))return false;
            const u64 step=value(entry+12,4);if((j+1==count)!=(step==0) || (step && (step<16 || step%4 || !range(a,step,~u64{0}))))return false;
            a+=step;
        }
        if((i+1==d.need_count)!=(next==0) || (next && (next<16 || next%4 || !range(at,next,~u64{0}))))return false;
        at+=next;
    }
    return true;
}
bool symbols(reader& r,const dynamic_info& d) {
    u8 h[16];if(!d.hash || !r.memory(d.hash,h,8))return false;
    const u64 buckets=value(h,4),count=value(h+4,4);
    if(!buckets || !count || buckets>262144 || count>262144
      || !r.segment(d.hash,8+4*(buckets+count),map_read) || d.symbol_size!=24
      || !r.segment(d.symbols,count*24,map_read))return false;
    r.image.symbol_count=static_cast<u32>(count);
    for(u64 i=0;i<buckets+count;++i)if(!r.memory(d.hash+8+4*i,h,4) || value(h,4)>=count)return false;
    if(d.gnu_hash) {
        if(!r.memory(d.gnu_hash,h,16))return false;
        const u64 n=value(h,4),base=value(h+4,4),bloom=value(h+8,4),shift=value(h+12,4);
        if(!n || n>262144 || base>count || !power(bloom) || bloom>262144 || shift>=64
          || !r.segment(d.gnu_hash,16+8*bloom+4*n,map_read))return false;
        bool nonempty=false;
        for(u64 i=0;i<n;++i) { if(!r.memory(d.gnu_hash+16+8*bloom+4*i,h,4))return false;
            const u64 b=value(h,4);if(b && (b<base || b>=count))return false;nonempty=nonempty || b!=0; }
        // An executable with only undefined dynamic symbols has no GNU hash
        // chains, even when symoffset is below the SysV nchain count.
        if(nonempty && (!r.segment(d.gnu_hash,16+8*bloom+4*n+4*(count-base),map_read)
          || !r.memory(d.gnu_hash+16+8*bloom+4*n+4*(count-base-1),h,4) || !(value(h,4)&1)))return false;
    }
    if(d.versions && !r.segment(d.versions,2*count,map_read))return false;
    // Validate the entire string table once in file order. ELF permits names
    // to share suffixes, so any in-range index is terminated within 4096 bytes
    // when every table string has this bound. Alternating dynsym, dynstr and
    // versym for every C++ symbol otherwise thrashes a bounded file-pin cache
    // and spends the startup deadline on redundant Files RPCs.
    u32 string_length=0;
    for(u64 at=0;at<d.string_bytes;) {
        u8 block[4096];
        const u64 remaining=d.string_bytes-at;
        const u32 amount=remaining<sizeof(block)?static_cast<u32>(remaining):sizeof(block);
        if(!r.memory(d.strings+at,block,amount) || (!at && block[0]))return false;
        for(u32 i=0;i<amount;++i) {
            if(!block[i])string_length=0;
            else if(++string_length>=4096)return false;
        }
        at+=amount;
    }
    if(string_length)return false;
    for(u64 i=0;i<count;++i) {
        u8 s[24];if(!r.memory(d.symbols+i*24,s,24) || value(s,4)>=d.string_bytes)return false;
        const u32 kind=s[4]&15,bind=s[4]>>4;const u64 shndx=value(s+6,2),address=value(s+8,8),bytes=value(s+16,8);
        if((kind>6 && kind!=10) || (bind>2 && bind!=10) || (s[5]&~3u))return false;
        if(shndx && shndx!=0xfff1) {
            if(shndx>=0xff00)return false;
            if(kind==6) { if(!r.image.tls_align || !range(address,bytes,r.image.tls_bytes))return false; }
            else if(!r.mapped(address,bytes,map_read))return false;
        }
    }
    if(d.versions) {
        for(u64 i=0;i<count;++i) {
            u8 v[2];if(!r.memory(d.versions+i*2,v,2))return false;const u16 index=static_cast<u16>(value(v,2)&0x7fff);
            bool known=index<=1;for(u32 j=0;j<r.image.version_count;++j)known=known || r.image.versions[j].index==index;
            if(!known)return false;
        }
    }
    return true;
}
bool relocations(reader& r,u64 table,u64 bytes,u64 entsize,bool plt,bool dynamic_tls_only) {
    if(!bytes)return table==0;
    if(!table || entsize!=24 || bytes%24 || bytes/24>262144 || !r.segment(table,bytes,map_read))return false;
    for(u64 at=0;at<bytes;at+=24) {
        u8 data[24];if(!r.memory(table+at,data,24))return false;
        const u64 address=value(data,8),info=value(data+8,8),addend=value(data+16,8);const u32 kind=static_cast<u32>(info),symbol=static_cast<u32>(info>>32);
        if(symbol>=r.image.symbol_count || (plt && kind!=7 && kind!=37))return false;
        if(kind==0)continue;
        // TPOFF64 requires static TLS; GNU TLSDESC may also allocate it. Native
        // workers do not join GNU's stack list for retroactive TLS updates.
        if(dynamic_tls_only && (kind==18 || kind==36))return false;
        if(kind!=1 && kind!=6 && kind!=7 && kind!=8 && kind!=16 && kind!=17 && kind!=18 && kind!=36 && kind!=37)return false;
        if(!r.mapped(address,kind==36?16:8,map_write))return false;
        if((kind==8 || kind==37) && symbol)return false;
        if(kind==37 && !r.mapped(addend,1,map_execute))return false;
        ++r.image.relocation_count;
    }return true;
}
bool packed_relocations(reader& r,const dynamic_info& d) {
    if(!d.relr_bytes)return !d.relr && !d.relr_size;
    if(!d.relr || d.relr_size!=8 || d.relr_bytes%8 || d.relr_bytes/8>262144 || !r.segment(d.relr,d.relr_bytes,map_read))return false;
    u64 base=0;bool have=false;
    for(u64 at=0;at<d.relr_bytes;at+=8) {
        u8 data[8];if(!r.memory(d.relr+at,data,8))return false;const u64 item=value(data,8);
        if(!(item&1)) { if(item%8 || !r.mapped(item,8,map_write) || (have && item<base))return false;base=item+8;have=true;++r.image.relocation_count; }
        else { if(!have || base>~u64{0}-63*8)return false;
            for(u32 bit=1;bit<64;++bit)if(item&(u64{1}<<bit)) { if(!r.mapped(base+(bit-1)*8,8,map_write))return false;++r.image.relocation_count; }
            base+=63*8;
        }
    }return true;
}
}

error inspect_elf(elf::read_exact_fn read,void* context,const generation& g,u32 index,elf_image& output) {
    output={};if(index>=g.header.object_count || !index)return error::role;
    const auto& expected=g.objects[index];
    const auto identity=inspect_identity(read,context,expected.file_bytes,expected.identity);
    if(identity!=error::none)return identity;
    reader r{read,context,expected.file_bytes,output};u8 header[64],program[56];
    if(!r.file(0,header,64))return error::io;
    output.entry=value(header+24,8);output.phoff=value(header+32,8);output.phnum=static_cast<u32>(value(header+56,2));
    if(output.phnum>64)return error::bounds;
    u64 dynamic_address=0,dynamic_bytes=0,relro_address=0,relro_bytes=0;u32 stacks=0,tls=0,phdrs=0;
    for(u32 i=0;i<output.phnum;++i) {
        if(!r.file(output.phoff+i*56,program,56))return error::io;
        const u32 type=static_cast<u32>(value(program,4)),flags=static_cast<u32>(value(program+4,4));
        const u64 offset=value(program+8,8),address=value(program+16,8),files=value(program+32,8),memory=value(program+40,8),align=value(program+48,8);
        if(flags&~7u || !range(offset,files,r.size) || !range(address,memory,generation_mapping_limit))return error::bounds;
        if(type==1) {
            if(!memory || files>memory || !(flags&4) || (flags&3)==3 || !power(align) || align<4096 || align>2097152
              || expected.bias%align || offset%align!=address%align || output.load_count==elf_load_limit)return error::header;
            const u64 begin=address&~u64{4095},end=(address+memory+4095)&~u64{4095};
            if(output.load_count && begin<output.span)return error::header;
            output.loads[output.load_count++]={offset,address,files,memory,flags};output.span=end;
        } else if(type==2) { if(dynamic_bytes || flags!=6 || !files || files!=memory || files%16 || files>16384)return error::header;dynamic_address=address;dynamic_bytes=files; }
        else if(type==6) { if(++phdrs!=1 || flags!=4 || offset!=output.phoff || files!=output.phnum*56 || memory!=files)return error::header;output.phaddr=address; }
        else if(type==7) { if(++tls!=1 || files>memory || !power(align) || align>4096)return error::header;output.tls_address=address;output.tls_bytes=memory;output.tls_align=align; }
        else if(type==0x6474e552) { if(relro_bytes || !memory || flags!=4)return error::header;relro_address=address;relro_bytes=memory; }
        else if(type==0x6474e551) { if(++stacks!=1 || flags!=6 || files || memory)return error::header; }
        else if(type!=0 && type!=3 && type!=4 && type!=0x6474e550 && type!=0x6474e553)return error::header;
    }
    if(!output.load_count || output.loads[0].address || output.loads[0].offset || output.span!=expected.span
       || !dynamic_bytes || !r.segment(dynamic_address,dynamic_bytes,map_read) || !relro_bytes
       || !r.mapped(relro_address,relro_bytes,map_write) || !stacks || (index==2 && !phdrs)
       || !r.segment(0,64,map_read) || !r.segment(output.phaddr,output.phnum*56,map_read)
       || (index<=2 && !r.mapped(output.entry,1,map_execute)))return error::header;
    dynamic_info d{};u64 seen[128]{};u32 seen_count=0,needed=0;bool ended=false;
    for(u64 at=0;at<dynamic_bytes;at+=16) {
        u8 data[16];if(!r.memory(dynamic_address+at,data,16))return error::io;
        const u64 tag=value(data,8),v=value(data+8,8);
        if(ended) { if(tag || v)return error::header;continue; }
        if(!tag) { if(v)return error::header;ended=true;continue; }
        if(tag!=1) { for(u32 i=0;i<seen_count;++i)if(seen[i]==tag)return error::duplicate;if(seen_count==128)return error::bounds;seen[seen_count++]=tag; }
        switch(tag) {
        case 1: ++needed;break;
        case 2:d.jmp_bytes=v;break;case 3:if(!r.mapped(v,8,map_write))return error::header;break;
        case 4:d.hash=v;break;case 5:d.strings=v;break;case 6:d.symbols=v;break;
        case 7:d.rela=v;break;case 8:d.rela_bytes=v;break;case 9:d.rela_size=v;break;
        case 10:d.string_bytes=v;break;case 11:d.symbol_size=v;break;
        case 12:d.init=v;break;case 13:d.fini=v;break;case 14:d.has_soname=true;d.soname=v;break;
        case 16:if(v)return error::header;break;case 20:d.plt_rel=v;break;case 21:if(v || index!=2)return error::header;break;
        case 23:d.jmp=v;break;case 24:if(v)return error::header;d.now=true;break;
        case 25:d.init_array=v;break;case 26:d.fini_array=v;break;case 27:d.init_bytes=v;break;case 28:d.fini_bytes=v;break;
        case 30:d.flags=v;break;case 32:d.preinit=v;break;case 33:d.preinit_bytes=v;break;
        case 35:d.relr_bytes=v;break;case 36:d.relr=v;break;case 37:d.relr_size=v;break;
        case 0x6ffffef5:d.gnu_hash=v;break;case 0x6ffffff0:d.versions=v;break;
        case 0x6ffffff9:d.relacount=v;break;case 0x6ffffffb:d.flags1=v;break;
        case 0x6ffffffc:d.defs=v;break;case 0x6ffffffd:d.def_count=v;break;
        case 0x6ffffffe:d.needs=v;break;case 0x6fffffff:d.need_count=v;break;
        default:return error::header;
        }
    }
    if(!ended || needed!=expected.needed_count || !d.string_bytes || d.string_bytes>generation_file_limit
       || !r.segment(d.strings,d.string_bytes,map_read) || (d.flags&~u64{0x1a}) || (d.flags1&~u64{0x08000009})
       || (d.jmp_bytes && !(d.now || (d.flags&8) || (d.flags1&1)))
       || (d.jmp_bytes && d.plt_rel!=7) || (d.relacount>d.rela_bytes/24))return error::header;
    char text[128]{};if(d.has_soname!=static_cast<bool>(expected.soname[0])
       || (d.has_soname && (!r.string(d.strings,d.string_bytes,d.soname,text) || !same(text,expected.soname))))return error::dependency;
    u32 edge=0;
    for(u64 at=0;at<dynamic_bytes;at+=16) { u8 data[16];if(!r.memory(dynamic_address+at,data,16))return error::io;
        if(value(data,8)==1 && (!r.string(d.strings,d.string_bytes,value(data+8,8),text)
           || !same(text,g.objects[expected.needed[edge++]].soname)))return error::dependency;
    }
    if((d.init && !r.mapped(d.init,1,map_execute)) || (d.fini && !r.mapped(d.fini,1,map_execute)))return error::header;
    const u64 arrays[][2]={{d.init_array,d.init_bytes},{d.fini_array,d.fini_bytes},{d.preinit,d.preinit_bytes}};
    for(const auto& a:arrays)if((a[0]==0)!=(a[1]==0) || a[1]%8 || (a[1] && !r.segment(a[0],a[1],map_read)))return error::header;
    if(index!=2 && d.preinit_bytes)return error::header;
    const bool online=g.header.version==generation_online_version && (g.header.online_mask&(1u<<index));
    if((online && (d.flags&0x10)) || !version_tables(r,d,g,index) || !symbols(r,d)
       || !relocations(r,d.rela,d.rela_bytes,d.rela_size,false,online)
       || !relocations(r,d.jmp,d.jmp_bytes,24,true,online) || !packed_relocations(r,d))return error::header;
    return error::none;
}

error check_versions(const generation& g,const elf_image* images) {
    if(!images)return error::bounds;
    for(u32 i=1;i<g.header.object_count;++i)for(u32 j=0;j<images[i].version_count;++j) {
        const auto& need=images[i].versions[j];if(need.definition)continue;
        bool found=false;
        for(u32 p=1;p<g.header.object_count;++p)if(same(g.objects[p].soname,need.provider))
            for(u32 v=0;v<images[p].version_count;++v) { const auto& def=images[p].versions[v];
                found=found || (def.definition && def.hash==need.hash && same(def.name,need.name)); }
        if(!found)return error::dependency;
    }return error::none;
}
}
