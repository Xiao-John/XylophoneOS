// SPDX-License-Identifier: Apache-2.0
#include "../../src/ports/browser_http/transport.hpp"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

namespace xos::sdk {
i64 syscall(u64,u64,u64,u64) { assert(false && "host framing test cannot perform native IO"); return -1; }
}
namespace {
struct source {
    std::string wire;
    size_t position=0,chunk=4096,calls=0;
    xos::i64 after=xos::net2::timeout;
};
xos::i64 read(void* context,unsigned char* bytes,xos::u32 capacity) {
    auto& value=*static_cast<source*>(context);++value.calls;
    if(value.position==value.wire.size()) return value.after;
    const size_t amount=std::min({value.chunk,static_cast<size_t>(capacity),value.wire.size()-value.position});
    std::memcpy(bytes,value.wire.data()+value.position,amount);value.position+=amount;
    return static_cast<xos::i64>(amount);
}
}
int main() {
    using namespace browser_http;using namespace xos;
    const std::string wire="HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\nbody";
    unsigned char buffer[512];response result{};
    for(size_t fragment:{size_t{1},size_t{7},size_t{4096}}) {
        source body{wire};body.chunk=fragment;
        assert(read_content_length_response(read,&body,buffer,sizeof(buffer),result)==0);
        assert(result.status==200 && result.body_length==4 && !std::memcmp(buffer+result.body_offset,"body",4));
        assert(body.position==wire.size() && body.calls==(wire.size()+fragment-1)/fragment);
        source eof{wire};eof.chunk=fragment;
        assert(read_framed_response(read,&eof,buffer,sizeof(buffer),result)==net2::timeout && !result.status);
        source closed{wire};closed.chunk=fragment;closed.after=0;
        assert(read_framed_response(read,&closed,buffer,sizeof(buffer),result)==0 && result.body_length==4);
    }
    source truncated{wire.substr(0,wire.size()-1)};truncated.after=0;
    assert(read_content_length_response(read,&truncated,buffer,sizeof(buffer),result)==net2::io && !result.status);
    source surplus{wire+"!"};
    assert(read_content_length_response(read,&surplus,buffer,sizeof(buffer),result)==net2::invalid && !result.status);
    source duplicate{"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nContent-Length: 4\r\n\r\nbody"};
    assert(read_content_length_response(read,&duplicate,buffer,sizeof(buffer),result)==net2::invalid && !result.status);
    source unframed{"HTTP/1.1 200 OK\r\n\r\nbody"};
    assert(read_content_length_response(read,&unframed,buffer,sizeof(buffer),result)==net2::unsupported && !result.status);
    source chunked{"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"};
    assert(read_content_length_response(read,&chunked,buffer,sizeof(buffer),result)==net2::unsupported && !result.status);
    source small{wire};
    assert(read_content_length_response(read,&small,buffer,wire.size()-1,result)==net2::resources && !result.status);
    std::puts("CLARKE_HTTP_FRAMING_PASS exact body, fragments, original EOF semantics, truncation, surplus, duplicate and unsupported framing");
}
