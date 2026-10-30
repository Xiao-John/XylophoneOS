// SPDX-License-Identifier: Apache-2.0
#include "../../src/ports/browser_http/http.hpp"
#include <stdio.h>
#include <string.h>

using namespace browser_http;
static unsigned checks = 0;
static bool check(bool ok, const char* name) {
    ++checks;
    if (!ok) printf("FAIL browser_http %u %s\n", checks, name);
    return ok;
}
static error response_for(const char* s, bool eof, response& r) {
    return parse_response(reinterpret_cast<const unsigned char*>(s), strlen(s), eof, r);
}
int main() {
    bool ok = true;
    url u, v;
    const char* absolute = "http://Example.Test:8080/a/b/../c?q=1#anchor";
    ok &= check(parse_url(absolute, strlen(absolute), u) == error::ok && !strcmp(u.host,"example.test") && u.port == 8080 && !strcmp(u.target,"/a/c?q=1"), "absolute_normalize");
    struct pair { const char* input; const char* output; } vectors[] = {
        {"g", "/a/g"}, {"./g", "/a/g"}, {"../g", "/g"}, {"../../g", "/g"},
        {"?y", "/a/c?y"}, {"#s", "/a/c?q=1"}, {"", "/a/c?q=1"},
        {"/a/./b/../", "/a/"}, {"g?y/../x", "/a/g?y/../x"},
        {"/a//b", "/a//b"}, {"/a/%2e%2e/b", "/a/%2e%2e/b"}
    };
    for (const auto& p : vectors) ok &= check(resolve(u, p.input, strlen(p.input), v) == error::ok && !strcmp(v.target,p.output), p.input);
    const char* invalid_urls[] = {"http://", "http://u@host/", "http://-bad/", "http://bad../", "http://a:0/", "http://a:65536/", "http://[::1]/", "http://a/%00", "http://a/%0d", "http://a/%", "http://a/\r\nInjected:x", "http://a\\b/", "http://a:999999999999999999999/"};
    for (const auto* p : invalid_urls) ok &= check(parse_url(p, strlen(p), v) == error::invalid, p);
    ok &= check(parse_url("https://a/",10,v) == error::unsupported, "https_refused");
    ok &= check(resolve(u,"javascript:alert(1)",19,v) == error::unsupported, "script_scheme_refused");
    ok &= check(resolve(u,"//other:90/z",12,v) == error::ok && !strcmp(v.host,"other") && v.port==90, "network_reference");
    char request[4096]; size_t size = 0;
    ok &= check(get_request(u, request, sizeof request, size) == error::ok && size < sizeof request, "request");
    request[size] = 0;
    ok &= check(!strcmp(request,"GET /a/c?q=1 HTTP/1.1\r\nHost: example.test:8080\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n"), "request_bytes");
    ok &= check(get_request(u,request,4,size) == error::too_large && size == 0,"request_capacity");
    v = u; strcpy(v.host,"a\r\nInjected:x");
    ok &= check(get_request(v,request,sizeof request,size) == error::invalid,"request_revalidates");
    const char* bad_hosts[] = {"a/b", "a?b", "a#b", "a:80", "a@b", "a b", "a\\b"};
    for (const auto* host : bad_hosts) {
        v = u; strcpy(v.host,host);
        ok &= check(get_request(v,request,sizeof request,size)==error::invalid && size==0,"request_invalid_host_component");
    }
    v = u; strcpy(v.host,"EXAMPLE.TEST");
    ok &= check(get_request(v,request,sizeof request,size)==error::ok,"request_uppercase_host");
    v = u; size_t host_pos=0;
    for (unsigned label=0;label<4;++label) {
        if(label) v.host[host_pos++]='.';
        for (unsigned j=0;j<(label==3?61u:63u);++j) v.host[host_pos++]='a';
    }
    v.host[host_pos]=0;
    ok &= check(host_pos==253 && get_request(v,request,sizeof request,size)==error::ok,"request_max_dns_host");
    v.host[253]='a';
    ok &= check(get_request(v,request,sizeof request,size)==error::invalid && size==0,"request_unterminated_host");
    v = u; strcpy(v.target,"/a/../z#not_sent");
    ok &= check(get_request(v,request,sizeof request,size)==error::ok && size>7 && !memcmp(request,"GET /z ",7),"request_strips_fragment");
    response r;
    const char* full = "HTTP/1.1 200 OK\r\nContent-Length: 5\r\nContent-Type: text/html\r\n\r\nHello";
    const size_t total = strlen(full);
    for (size_t i = 0; i < total; ++i) {
        ok &= check(parse_response(reinterpret_cast<const unsigned char*>(full),i,false,r) == error::need_more,"partial");
        ok &= check(parse_response(reinterpret_cast<const unsigned char*>(full),i,true,r) == error::truncated,"premature_eof");
    }
    ok &= check(response_for(full,true,r) == error::ok && r.status == 200 && r.body_length == 5 && !memcmp(full+r.body_offset,"Hello",5),"complete_body");
    const char* bad[] = {
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length : 1\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length: +1\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length: 1,1\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\n x:y\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nxx",
        "HTTP/1.1 204 No Content\r\nContent-Length: 1\r\n\r\nx",
        "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nLocation: /a\r\nLocation: /b\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nX: a\nb\r\n\r\n",
    };
    for (const auto* p : bad) ok &= check(response_for(p,true,r)==error::invalid,"malformed");
    const char* unsupported[] = {
        "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
        "HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Encoding: gzip\r\n\r\n",
        "HTTP/1.1 200 OK\r\n\r\nclosed_body",
        "HTTP/1.1 100 Continue\r\n\r\n"
    };
    for (const auto* p : unsupported) ok &= check(response_for(p,true,r)==error::unsupported,"unsupported_framing");
    ok &= check(response_for("HTTP/1.0 204 Empty\r\n\r\n",true,r)==error::ok && r.body_length==0,"204");
    ok &= check(response_for("HTTP/1.1 304 Cached\r\nContent-Length: 100\r\n\r\n",true,r)==error::ok && r.body_length==0,"304_metadata");
    ok &= check(response_for("HTTP/1.1 200 OK\r\nContent-Length: 999999999999999999999999\r\n\r\n",true,r)==error::too_large,"length_overflow");
    ok &= check(response_for("HTTP/1.1 302 Found\r\nContent-Length: 0\r\nLocation: ../next\r\n\r\n",true,r)==error::ok,"redirect_response");
    unsigned redirects = 0;
    for (unsigned i = 0; i < 5; ++i) ok &= check(redirect(u,r,redirects,v)==error::ok && !strcmp(v.target,"/next"),"redirect_five");
    ok &= check(redirect(u,r,redirects,v)==error::too_large && redirects==5,"redirect_loop_limit");
    ok &= check(parse_response(nullptr,1,true,r)==error::invalid,"null_span");
    static unsigned char header_limit[max_headers+1];
    memset(header_limit,'x',sizeof header_limit);
    ok &= check(parse_response(header_limit,sizeof header_limit,false,r)==error::too_large,"header_budget");
    ok &= check(parse_response(header_limit,max_headers+max_body+1,false,r)==error::too_large,"total_budget_before_read");
    const char binary[]="HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\na\0b";
    ok &= check(parse_response(reinterpret_cast<const unsigned char*>(binary),sizeof binary-1,true,r)==error::ok && r.body_length==3,"binary_body");
    char fields[2048]; strcpy(fields,"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n");
    for(unsigned i=0;i<64;++i) strcat(fields,"X: y\r\n");
    strcat(fields,"\r\n");
    ok &= check(response_for(fields,true,r)==error::too_large,"field_budget");
    // Deterministic malformed bytes exercise bounded parsing without heap use.
    unsigned char fuzz[1024]; uint32_t state = 0x584f5301u;
    for (unsigned iteration = 0; iteration < 4096; ++iteration) {
        for (size_t i=0;i<sizeof fuzz;++i) { state=state*1664525u+1013904223u; fuzz[i]=static_cast<unsigned char>(state>>24); }
        (void)parse_response(fuzz,iteration%sizeof fuzz,true,r);
        (void)parse_url(reinterpret_cast<const char*>(fuzz),iteration%sizeof fuzz,v);
    }
    for (size_t i=0;i<total;++i) for(unsigned c=0;c<256;++c) {
        memcpy(fuzz,full,total);fuzz[i]=static_cast<unsigned char>(c);
        (void)parse_response(fuzz,total,true,r);
    }
    printf("browser_http checks=%u malformed_vectors=4096 result=%s\n",checks,ok?"PASSED":"FAILED");
    return ok?0:1;
}
