// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/fat_resource_import.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

namespace {
using namespace xos;
using namespace xos::user::pumpkin;
constexpr char source[] = "/input/public.bin";
constexpr u32 pinned = 9;
struct file_boundary {
    u32 length = named_resource_bytes;
    i64 open_result = 0;
    i64 short_by = 0;
    i64 close_result = 0;
    u32 reads = 0;
    u32 closes = 0;
} fixture;
}

i64 file::client::open(const char* path, u32 flags, u32& handle, u32& length, u32& version) {
    assert(std::strcmp(path, source) == 0 && flags == (file::read_only | file::open_pin));
    if (fixture.open_result) { return fixture.open_result; }
    handle = pinned;
    length = fixture.length;
    version = 1;
    return 0;
}
i64 file::client::read_at(u32 handle, void* bytes, u32 length, u64 offset) {
    assert(handle == pinned && offset == 0 && length == fixture.length && length <= named_resource_bytes);
    ++fixture.reads;
    auto* output = static_cast<u8*>(bytes);
    for (u32 index = 0; index < length; ++index) { output[index] = static_cast<u8>(index * 11); }
    return static_cast<i64>(length) - fixture.short_by;
}
i64 file::client::close(u32 handle) {
    assert(handle == pinned);
    ++fixture.closes;
    return fixture.close_result;
}

int main() {
    file::client files;
    named_resource_data value{};
    assert(read_fat_resource(files, source, value) && value.valid() && value.length == named_resource_bytes);
    assert(value.bytes[0] == 0 && value.bytes[31] == static_cast<u8>(31 * 11));
    assert(fixture.reads == 1 && fixture.closes == 1);

    fixture = {.length = 1};
    assert(read_fat_resource(files, source, value) && value.valid() && value.length == 1 && value.bytes[0] == 0);
    assert(fixture.reads == 1 && fixture.closes == 1);

    fixture = {.length = named_resource_bytes + 1};
    assert(!read_fat_resource(files, source, value) && value.empty());
    assert(!fixture.reads && fixture.closes == 1);
    fixture = {.length = 0};
    assert(!read_fat_resource(files, source, value) && value.empty());
    assert(!fixture.reads && fixture.closes == 1);

    fixture = {.open_result = -1};
    assert(!read_fat_resource(files, source, value) && value.empty());
    assert(!fixture.reads && !fixture.closes);
    fixture = {.short_by = 1};
    assert(!read_fat_resource(files, source, value) && value.empty());
    assert(fixture.reads == 1 && fixture.closes == 1);
    fixture = {.close_result = -1};
    assert(!read_fat_resource(files, source, value) && value.empty());
    assert(fixture.reads == 1 && fixture.closes == 1);
    std::puts("PASS FAT import pins one object and only publishes a complete binary read after handle close");
}
