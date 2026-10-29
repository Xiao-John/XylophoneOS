// SPDX-License-Identifier: Apache-2.0
#include "blur.hpp"
namespace aurora {
bool box_blur_argb32(const std::uint32_t *in,std::uint32_t *out,std::uint32_t *tmp,
                    std::size_t w,std::size_t h,std::size_t cap,unsigned r) {
    if(!in || !out || !tmp || in==out || in==tmp || out==tmp || !w || !h ||
       w>4096 || h>4096 || cap/w<h || !r || r>32)return false;
    const unsigned n=r*2+1;
    auto clamp=[](long long x,std::size_t bound)->std::size_t {
        return x<0?0:static_cast<std::size_t>(x)>=bound?bound-1:static_cast<std::size_t>(x);
    };
    for(int pass=0;pass<2;++pass){
        const auto *src=pass?tmp:in;auto *dest=pass?out:tmp;
        const auto lines=pass?w:h, length=pass?h:w;
        auto index=[=](std::size_t line,std::size_t pos){return pass?pos*w+line:line*w+pos;};
        for(std::size_t line=0;line<lines;++line){
            unsigned sums[4]{};
            auto add=[&](std::uint32_t pixel,bool subtract){for(unsigned c=0;c<4;++c){const auto v=(pixel>>(c*8))&255u;if(subtract)sums[c]-=v;else sums[c]+=v;}};
            for(long long k=-static_cast<long long>(r);k<=r;++k)add(src[index(line,clamp(k,length))],false);
            for(std::size_t pos=0;pos<length;++pos){
                std::uint32_t pixel=0;for(unsigned c=0;c<4;++c)pixel|=((sums[c]+n/2)/n)<<(c*8);
                dest[index(line,pos)]=pixel;
                add(src[index(line,clamp(static_cast<long long>(pos)-r,length))],true);
                add(src[index(line,clamp(static_cast<long long>(pos)+r+1,length))],false);
            }
        }
    }
    return true;
}
}
