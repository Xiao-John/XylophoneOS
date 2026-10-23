#pragma once
#include <xos/file_abi.hpp>

namespace xos::file {
struct entry {
    char name[max_name];
    u32 size;
    u32 version;
};

class Client {
public:
    bool init();
    i64 ping();
    i64 list(entry* entries, u32 capacity, u32& count);
    i64 stat(const char* name, u32& size, u32& version);
    i64 open(const char* name, u32 flags, u32& handle, u32& size, u32& version);
    i64 read(u32 handle, void* data, u32 length);
    i64 write(u32 handle, const void* data, u32 length);
    i64 seek(u32 handle, u32 offset);
    i64 close(u32 handle);
    i64 replace(const char* name, const void* data, u32 length);
    i64 read_all(const char* name, void* data, u32 capacity, u32& length);
    i64 remove(const char* name);
    i64 sync();
    i64 begin_replace(const char* name, u32 length);
    i64 abort_replace();

private:
    i64 call(op operation);
    u32 send_handle_;
    u32 recv_handle_;
    u32 request_id_;
    request request_;
    response response_;
};
}
