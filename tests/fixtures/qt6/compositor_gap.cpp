// SPDX-License-Identifier: Apache-2.0
// Existing display-v1 only: no guessed syscall, service operation or ABI.
#include <xos/display_client.hpp>
#include <cstdio>
#include <cstring>
int main(int argc,char **argv) {
    xos::sdk::display_client client;
    const auto r=client.open();
    const bool occupied=argc>1 && std::strcmp(argv[1],"occupied")==0;
    std::printf("COMPOSITOR_GAP connect=%lld expected=%d\n",(long long)r,occupied?-16:0);
    if(r!=(occupied?-16:0))return 1;
    if(!occupied){
        xos::display_mode mode{};if(client.mode(mode))return 2;
        // Final output supports XRGB; there is no alpha/window transport in v1.
        std::printf("COMPOSITOR_GAP mode=%ux%u format=%u\n",mode.width,mode.height,unsigned(mode.format));
        if(client.close())return 3;
    }
    // An ordinary process cannot obtain the service-only request-present right.
    const auto denied=xos::sdk::syscall(xos::sys_display_present,0);
    std::printf("COMPOSITOR_GAP direct_present=%lld\n",(long long)denied);
    return denied==-1?0:4;
}
