// SPDX-License-Identifier: Apache-2.0
#include "../src/ports/qt6/aurora/blur.hpp"
#include <vector>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <algorithm>
int main(){
    std::uint32_t seed=7;unsigned cases=0;
    auto random=[&]{seed=seed*1664525+1013904223;return seed;};
    for(unsigned h=1;h<=9;++h)for(unsigned w=1;w<=11;++w)for(unsigned r:{1u,2u,6u,32u}){
        std::vector<std::uint32_t> in(w*h),out(w*h),tmp(w*h),first(w*h),expected(w*h);
        for(auto &p:in){const auto alpha=random()&255;p=alpha<<24;for(unsigned c=0;c<3;++c)p|=(random()%(alpha+1))<<(8*c);}
        // Independent direct-neighborhood definition, with rounding after each pass.
        for(int pass=0;pass<2;++pass){auto &src=pass?first:in;auto &dst=pass?expected:first;
            for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x){unsigned sums[4]{};
                for(int k=-int(r);k<=int(r);++k){const auto xx=pass?x:unsigned(std::clamp(int(x)+k,0,int(w)-1));const auto yy=pass?unsigned(std::clamp(int(y)+k,0,int(h)-1)):y;
                    for(unsigned c=0;c<4;++c)sums[c]+=(src[yy*w+xx]>>(c*8))&255;}
                std::uint32_t p=0;for(unsigned c=0;c<4;++c)p|=((sums[c]+r)/(2*r+1))<<(8*c);dst[y*w+x]=p;
            }
        }
        assert(aurora::box_blur_argb32(in.data(),out.data(),tmp.data(),w,h,in.size(),r));assert(out==expected);
        for(auto p:out)for(unsigned c=0;c<3;++c)assert(((p>>(c*8))&255)<=(p>>24));++cases;
    }
    std::uint32_t a=0,b=0,c=0;
    assert(!aurora::box_blur_argb32(nullptr,&b,&c,1,1,1,1));
    assert(!aurora::box_blur_argb32(&a,&a,&c,1,1,1,1));
    assert(!aurora::box_blur_argb32(&a,&b,&c,4097,1,999999,1));
    assert(!aurora::box_blur_argb32(&a,&b,&c,1,1,0,1));
    assert(!aurora::box_blur_argb32(&a,&b,&c,1,1,1,0));
    assert(!aurora::box_blur_argb32(&a,&b,&c,1,1,1,33));
    std::printf("AURORA_BLUR_CASES %u exact neighborhood vectors + 6 rejections PASS\n",cases);
}
