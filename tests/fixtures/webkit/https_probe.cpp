// SPDX-License-Identifier: Apache-2.0
#include "https.hpp"
#include "tls_policy.hpp"
#include <xos/sdk.hpp>
#include <xos/fault_sha256.hpp>
#include <cstdio>
#include <cstring>
#include <ctime>

int main(int argc, char** argv)
{
    using namespace xos;
    if (argc != 4 || std::strlen(argv[3]) != 32) return 2;
    u64 service = 0;
    for (const char* value=argv[1]; *value; ++value) {
        if (*value<'0' || *value>'9' || service > (~u64{0}-9)/10) return 2;
        service = service*10 + static_cast<u64>(*value-'0');
    }
    if (!service) return 2;
    char url[512];
    const int length=std::snprintf(url,sizeof(url),"https://%s:%u/%s",clarke_tls_host,clarke_tls_port,argv[3]);
    browser_http::url target{};
    if (length <= 0 || static_cast<std::size_t>(length)>=sizeof(url) ||
        browser_http::parse_url(url,length,target)!=browser_http::error::ok) return 3;
    const i64 before=sdk::syscall(sys_clock_monotonic);
    if (before < 0) return 3;
    unsigned char buffer[8192]{}; browser_http::response response{};
    const i64 result=clarke_https::fetch(service,target,buffer,sizeof(buffer),
        static_cast<u64>(before)+3'000'000'000,response);
    const i64 after=sdk::syscall(sys_clock_monotonic);
    const bool accepted=!std::strcmp(argv[2],"valid") || !std::strcmp(argv[2],"server-close");
    const bool certificate=!std::strcmp(argv[2],"wrong-host") || !std::strcmp(argv[2],"unknown-ca") ||
        !std::strcmp(argv[2],"expired");
    const bool stalled=!std::strcmp(argv[2],"stall");
    const bool truncated=!std::strcmp(argv[2],"truncated");
    if (!accepted && !certificate && !stalled && !truncated) return 2;
    const bool empty=!response.status && !response.body_offset && !response.body_length;
    const bool pass=after>=before && after-before<10'000'000'000 &&
        (accepted ? (!result && response.status==200 && response.body_length==32 &&
            !std::memcmp(buffer+response.body_offset,argv[3],32)) :
         certificate ? (result==net2::denied && empty) :
         stalled ? (result==net2::timeout && empty) : (result==net2::io && empty));
    std::printf("CLARKE_HTTPS scenario=%s result=%lld status=%u bytes=%zu elapsed_ns=%lld realtime=%lld pass=%u\n",
        argv[2],static_cast<long long>(result),response.status,response.body_length,
        static_cast<long long>(after-before),static_cast<long long>(std::time(nullptr)),pass ? 1u : 0u);
    return pass ? 0 : 4;
}
