// SPDX-License-Identifier: Apache-2.0
// Adapted from src/user/programs/xypm_native.hpp for the FB0 fixture.
#pragma once
#include <xos/abi_types.hpp>
class sha256 {
    xos::u32 state_[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                           0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    xos::u64 bytes_ = 0;
    xos::u8 block_[64]{};
    xos::usize used_ = 0;
    static xos::u32 rotate(xos::u32 value, unsigned count) { return (value >> count) | (value << (32-count)); }
    void transform(const xos::u8* input) {
        static constexpr xos::u32 k[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        xos::u32 w[64];
        for (unsigned i=0;i<16;++i) w[i]=(xos::u32(input[i*4])<<24)|(xos::u32(input[i*4+1])<<16)|(xos::u32(input[i*4+2])<<8)|input[i*4+3];
        for (unsigned i=16;i<64;++i) { xos::u32 a=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3); xos::u32 b=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10); w[i]=w[i-16]+a+w[i-7]+b; }
        xos::u32 a=state_[0],b=state_[1],c=state_[2],d=state_[3],e=state_[4],f=state_[5],g=state_[6],h=state_[7];
        for (unsigned i=0;i<64;++i) { xos::u32 s1=rotate(e,6)^rotate(e,11)^rotate(e,25), ch=(e&f)^(~e&g); xos::u32 t1=h+s1+ch+k[i]+w[i]; xos::u32 s0=rotate(a,2)^rotate(a,13)^rotate(a,22), maj=(a&b)^(a&c)^(b&c); xos::u32 t2=s0+maj; h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2; }
        state_[0]+=a;state_[1]+=b;state_[2]+=c;state_[3]+=d;state_[4]+=e;state_[5]+=f;state_[6]+=g;state_[7]+=h;
    }
public:
    void update(const void* source, xos::usize length) {
        const auto* input=static_cast<const xos::u8*>(source); bytes_+=length;
        while (length) { xos::usize n=64-used_; if(n>length)n=length; for(xos::usize i=0;i<n;++i)block_[used_+i]=input[i];used_+=n;input+=n;length-=n;if(used_==64){transform(block_);used_=0;} }
    }
    void finish(xos::u8 output[32]) {
        const xos::u64 bits=bytes_*8; block_[used_++]=0x80;
        if(used_>56){while(used_<64)block_[used_++]=0;transform(block_);used_=0;}
        while(used_<56)block_[used_++]=0;
        for(unsigned i=0;i<8;++i) { block_[63-i]=xos::u8(bits>>(i*8)); }
        transform(block_);
        for(unsigned i=0;i<8;++i){output[i*4]=xos::u8(state_[i]>>24);output[i*4+1]=xos::u8(state_[i]>>16);output[i*4+2]=xos::u8(state_[i]>>8);output[i*4+3]=xos::u8(state_[i]);}
    }
};
inline void hex_digest(const xos::u8 digest[32], char output[65]) {
    static constexpr char hex[]="0123456789abcdef";
    for(unsigned i=0;i<32;++i){output[i*2]=hex[digest[i]>>4];output[i*2+1]=hex[digest[i]&15];}output[64]=0;
}
