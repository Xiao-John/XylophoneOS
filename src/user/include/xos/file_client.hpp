// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/file_abi.hpp>

namespace xos::file {
struct entry {
    char name[max_name];
    u32 size;
    u32 version;
    bool directory;
};

class Client {
public:
    bool init();
    i64 ping();
    i64 list(entry* entries, u32 capacity, u32& count);
    i64 list(const char* path, entry* entries, u32 capacity, u32& count, u32& cursor);
    i64 stat(const char* path, u32& size, u32& version);
    i64 stat_info(const char* path, u32& size, u32& attributes);
    i64 stat_info(const char* path, u32& size, u32& attributes, u32& identity);
    i64 open(const char* path, u32 flags, u32& handle, u32& size, u32& version);
    i64 fstat(u32 handle, u32& size, u32& attributes);
    i64 fstat(u32 handle, u32& size, u32& attributes, u32& identity);
    i64 read(u32 handle, void* data, u32 length);
    i64 write(u32 handle, const void* data, u32 length);
    i64 seek(u32 handle, u32 offset);
    i64 close(u32 handle);
    i64 replace(const char* path, const void* data, u32 length);
    i64 read_all(const char* path, void* data, u32 capacity, u32& length);
    i64 remove(const char* path);
    i64 mkdir(const char* path);
    i64 rename(const char* old_path, const char* new_path);
    i64 block_bench(u32 length);
    i64 sync();
    i64 begin_replace(const char* path, u32 length);
    i64 chunk_replace(u32 offset, const void* data, u32 length);
    i64 commit_replace();
    i64 abort_replace();

private:
    i64 set_path(const char* path, char* target, u32& length);
    i64 call(op operation);
    u32 send_handle_;
    u32 recv_handle_;
    u32 request_id_;
    request request_;
    response response_;
};
}
