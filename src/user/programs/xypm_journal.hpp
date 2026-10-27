// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>

// Persistent P2 journal v1. All integer fields are little endian on the
// registered x86-64 profile; the hash covers the header prefix and all rows.
namespace xypm_journal {
constexpr uint32_t version = 1;
constexpr uint32_t max_records = 16386; // union of old and new files plus db/index
constexpr uint32_t max_directories = 32768;
constexpr uint32_t old_present = 1;
constexpr uint32_t new_present = 2;
constexpr uint32_t remove_on_rollback = 1;
constexpr uint32_t remove_after_commit = 2;
constexpr char marker[] = "/var/lib/xypm/transaction";
constexpr char data_dir[] = "/var/lib/xypm/txdata";
constexpr char old_dir[] = "/var/lib/xypm/txdata/old";
constexpr char new_dir[] = "/var/lib/xypm/txdata/new";
constexpr char committed[] = "/var/lib/xypm/txdata/committed";
constexpr char commit_final[] = "/var/lib/xypm/transaction_commit";
constexpr char commit_temp[] = "/var/lib/xypm/txdata/commit.tmp";
constexpr char applying[] = "/var/lib/xypm/txdata/applying";
constexpr char preparing[] = "/var/lib/xypm/txdata/prepare";
constexpr char journal_temp[] = "/var/lib/xypm/txdata/journal.tmp";
constexpr char reserve[] = "/var/lib/xypm/txdata/reserve";
constexpr char reserve2[] = "/var/lib/xypm/txdata/reserve2";
inline constexpr char prepare_magic[8] = {'X','Y','P','P','R','E','1',0};
inline constexpr char applying_magic[8] = {'X','Y','P','A','P','P','1',0};
struct header { char magic[8]; uint32_t version; uint32_t record_count; uint32_t directory_count; uint32_t reserved; uint8_t digest[32]; };
struct record { char path[256]; uint32_t flags; uint32_t old_size; uint32_t new_size; uint8_t old_hash[32]; uint8_t new_hash[32]; };
struct directory { char path[256]; uint32_t flags; };
struct commit_record { char magic[8]; uint8_t journal_hash[32]; uint8_t self_hash[32]; };
static_assert(sizeof(header)==56 && sizeof(record)==332 && sizeof(directory)==260 && sizeof(commit_record)==72);
inline constexpr char magic[8] = {'X','Y','P','T','X','N','1',0};
inline constexpr char commit_magic[8] = {'X','Y','P','C','M','T','1',0};
class sha256 {
    uint32_t state_[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    uint64_t bytes_ = 0; uint8_t block_[64]{}; size_t used_ = 0;
    static uint32_t rotate(uint32_t v, unsigned n) { return (v >> n) | (v << (32-n)); }
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
        uint32_t w[64]; for (unsigned i=0;i<16;++i) w[i]=(uint32_t(input[i*4])<<24)|(uint32_t(input[i*4+1])<<16)|(uint32_t(input[i*4+2])<<8)|input[i*4+3];
        for (unsigned i=16;i<64;++i) { uint32_t a=rotate(w[i-15],7)^rotate(w[i-15],18)^(w[i-15]>>3); uint32_t b=rotate(w[i-2],17)^rotate(w[i-2],19)^(w[i-2]>>10); w[i]=w[i-16]+a+w[i-7]+b; }
        uint32_t a=state_[0],b=state_[1],c=state_[2],d=state_[3],e=state_[4],f=state_[5],g=state_[6],h=state_[7];
        for(unsigned i=0;i<64;++i){uint32_t s1=rotate(e,6)^rotate(e,11)^rotate(e,25),ch=(e&f)^(~e&g);uint32_t t1=h+s1+ch+k[i]+w[i];uint32_t s0=rotate(a,2)^rotate(a,13)^rotate(a,22),maj=(a&b)^(a&c)^(b&c);uint32_t t2=s0+maj;h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}
        state_[0]+=a;state_[1]+=b;state_[2]+=c;state_[3]+=d;state_[4]+=e;state_[5]+=f;state_[6]+=g;state_[7]+=h;
    }
public:
    void update(const void* source,size_t length) {const auto* input=static_cast<const uint8_t*>(source);bytes_+=length;while(length){size_t n=64-used_;if(n>length)n=length;memcpy(block_+used_,input,n);used_+=n;input+=n;length-=n;if(used_==64){transform(block_);used_=0;}}}
    void finish(uint8_t output[32]) {uint64_t bits=bytes_*8;block_[used_++]=0x80;if(used_>56){while(used_<64)block_[used_++]=0;transform(block_);used_=0;}while(used_<56)block_[used_++]=0;for(unsigned i=0;i<8;++i)block_[63-i]=uint8_t(bits>>(i*8));transform(block_);for(unsigned i=0;i<8;++i){output[i*4]=uint8_t(state_[i]>>24);output[i*4+1]=uint8_t(state_[i]>>16);output[i*4+2]=uint8_t(state_[i]>>8);output[i*4+3]=uint8_t(state_[i]);}}
};
}
