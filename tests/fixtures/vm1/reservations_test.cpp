// SPDX-License-Identifier: Apache-2.0
#include "src/kernel/core/anonymous_reservations.hpp"
#include <cassert>
#include <cstdio>
using namespace xos;
using namespace xos::anonymous_vm;
static reservations state;
int main() {
    request info{1,64,0,0,0,0,0,0,0,0,0};
    assert(state.apply(info,false)==0); info.flags=1; assert(state.apply(info,false)==invalid);
    request bad{1,64,1,1,arena_begin,0,page,0,0,0,0};
    assert(state.apply(bad,true)==invalid);
    request r{1,64,1,1,arena_begin,4*page,page,0,0,0,0};
    assert(state.apply(r,false)==static_cast<i64>(arena_begin));
    assert(state.apply(r,false)==collision);
    assert(state.unmap(arena_begin+page,2*page)==0);
    assert(state.count()==2 && state.bytes()==2*page);
    assert(state.reserve(arena_begin+page,2*page,page,true)==static_cast<i64>(arena_begin+page));
    assert(state.count()==1 && state.bytes()==4*page);
    assert(state.unmap(arena_begin,4*page)==0 && state.count()==0);
    r.reserved1=1; assert(state.apply(r,false)==invalid); r.reserved1=0;
    assert(state.apply(r,true)==closing);
    assert(state.reserve(arena_end-page,2*page,page,true)==invalid);
    assert(state.reserve(arena_begin, page,3*page,true)==invalid);
    assert(state.reserve(arena_begin, max_reservation+page,page,true)==invalid);
    assert(state.reserve(arena_begin,max_reservation,page,true)==static_cast<i64>(arena_begin));
    assert(state.reserve(arena_begin+max_reservation,max_reservation,page,true)==static_cast<i64>(arena_begin+max_reservation));
    assert(state.reserve(arena_begin+2*max_reservation,page,page,true)==resources);
    state.clear();
    for(u32 i=0;i<256;++i) assert(state.reserve(arena_begin+i*3*page,page,page,true)>=0);
    assert(state.count()==256);
    assert(state.reserve(arena_begin+800*page,page,page,true)==resources);
    assert(state.unmap(arena_begin,256*3*page)==0 && state.count()==0);
    assert(state.reserve(arena_begin,3*page,page,true)>=0);
    for(u32 i=1;i<256;++i) assert(state.reserve(arena_begin+(i*3+1)*page,page,page,true)>=0);
    assert(state.count()==256);
    auto old=state.bytes(); assert(state.unmap(arena_begin+page,page)==resources);
    assert(state.count()==256 && state.bytes()==old && state.at(0).end==arena_begin+3*page);
    state.clear(); bool bits[512]{}; u32 rng=0x19ac731u;
    for(u32 n=0;n<20000;++n) {
        rng=rng*1664525u+1013904223u; u32 start=(rng>>8)%500;
        rng=rng*1664525u+1013904223u; u32 size=(rng>>16)%12+1;
        const u64 base=arena_begin+start*page;
        if((rng>>20)&1) {
            bool free=true;for(u32 i=start;i<start+size;++i) free=free&&!bits[i];
            i64 result=state.reserve(base,size*page,page,true);
            if(free) { assert(result==static_cast<i64>(base));for(u32 i=start;i<start+size;++i)bits[i]=true; }
            else assert(result==collision);
        } else {
            assert(state.unmap(base,size*page)==0);
            for(u32 i=start;i<start+size;++i)bits[i]=false;
        }
        u64 total=0; u32 idx=0;
        for(u32 i=0;i<512;++i) {
            const u64 addr=arena_begin+i*page;
            while(idx<state.count() && state.at(idx).end<=addr)++idx;
            bool actual=idx<state.count() && state.at(idx).begin<=addr && state.at(idx).end>addr;
            assert(actual==bits[i]);if(bits[i])total+=page;
        }
        assert(total==state.bytes());
    }
    std::puts("PASS VM1 bounded reservations, rollback and differential sequences");
}
