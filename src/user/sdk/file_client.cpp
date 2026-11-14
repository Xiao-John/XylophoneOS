// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <xos/text.hpp>

extern "C" void xos_file_session_lock() __attribute__((weak));
extern "C" void xos_file_session_unlock() __attribute__((weak));
extern "C" xos::u32 xos_file_request_id() __attribute__((weak));
namespace xos::file {
namespace {
struct session_guard {
    session_guard() { if (xos_file_session_lock) { xos_file_session_lock(); } }
    ~session_guard() { if (xos_file_session_unlock) { xos_file_session_unlock(); } }
};
u32 fallback_request_id;
i64 status_value(status code) { return static_cast<i64>(code); }
}

bool client::init() {
    session_guard guard;
    send_handle_ = 0;
    recv_handle_ = 0;
    request_id_ = 0;
    owner_pid_ = 0;
    if (sdk::ipc_handles(send_handle_, recv_handle_) != 0 ||
        send_handle_ == 0 || recv_handle_ == 0) { return false; }
    owner_pid_ = sdk::pid();
    return true;
}

i64 client::call(op operation) {
    const u64 caller = sdk::pid();
    if (owner_pid_ != caller) {
        // A fork copies arbitrary client objects, including loader and
        // application instances. Rebind endpoints without clearing the
        // request that this operation has already prepared.
        u32 send = 0, receive = 0;
        if (sdk::ipc_handles(send, receive) != 0 || send == 0 || receive == 0) {
            return status_value(status::io);
        }
        send_handle_ = send;
        recv_handle_ = receive;
        request_id_ = 0;
        owner_pid_ = caller;
    }
    request_.magic = request_magic;
    request_.version = abi_version;
    request_.operation = static_cast<u16>(operation);
    request_.request_id = xos_file_request_id ? xos_file_request_id()
        : fallback_request_id == 0xffffffffu ? 0 : ++fallback_request_id;
    if (request_.request_id == 0) { return status_value(status::io); }
    if (sdk::ipc_send(send_handle_, &request_, sizeof(request_)) < 0) {
        return status_value(status::io);
    }
    for (u32 attempt = 0; attempt < 8192; ++attempt) {
        const i64 received = sdk::ipc_recv(recv_handle_, &response_, sizeof(response_));
        if (received == static_cast<i64>(sizeof(response_)) &&
            response_.magic == response_magic && response_.version == abi_version &&
            response_.request_id == request_.request_id) {
            if (response_.length > sizeof(response_.data)) {
                return status_value(status::io);
            }
            return response_.status_code;
        }
        sdk::yield();
    }
    return status_value(status::would_block);
}

i64 client::set_path(const char* path, char* target, u32& length) {
    if (path == nullptr) { return status_value(status::invalid); }
    length = 0;
    while (length < max_name && path[length] != '\0') {
        const u8 c = static_cast<u8>(path[length]);
        if (c == 0x7f || c < 0x20) { return status_value(status::invalid); }
        target[length] = path[length];
        ++length;
    }
    if (length == 0 || length >= max_name || path[length] != '\0') {
        return status_value(status::invalid);
    }
    if (!xos::text::valid(path, length)) { return status_value(status::invalid); }
    target[length] = '\0';
    return 0;
}

i64 client::ping() {
    session_guard guard;
    request_ = request{};
    return call(op::ping);
}

i64 client::list(const char* path, entry* entries, u32 capacity, u32& count, u32& cursor) {
    session_guard guard;
    count = 0;
    if (entries == nullptr || capacity == 0) {
        return status_value(status::invalid);
    }
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.name_length = path_length;
    request_.offset = cursor;
    request_.flags = list_directories;
    request_.length = capacity;
    const i64 result = call(op::list);
    if (result != 0) { return result; }

    return decode_list(entries, capacity, count, cursor);
}

i64 client::list(u32 directory_handle, entry* entries, u32 capacity, u32& count, u32& cursor) {
    session_guard guard;
    count = 0;
    if (entries == nullptr || capacity == 0 || directory_handle == 0) { return status_value(status::invalid); }
    request_ = request{};
    request_.handle = directory_handle;
    request_.offset = cursor;
    request_.flags = list_directories;
    request_.length = capacity;
    const i64 result = call(op::list);
    return result == 0 ? decode_list(entries, capacity, count, cursor) : result;
}

i64 client::decode_list(entry* entries, u32 capacity, u32& count, u32& cursor) {
    u32 position = 0;
    while (position < response_.length) {
        if (response_.length - position < list_record_header_size || count >= capacity) {
            return status_value(status::io);
        }
        const u16 name_length = static_cast<u16>(
            static_cast<u16>(response_.data[position]) |
            static_cast<u16>(static_cast<u16>(response_.data[position + 1]) << 8));
        const u8 attributes = response_.data[position + 2];
        const u32 size = static_cast<u32>(response_.data[position + 3]) |
            (static_cast<u32>(response_.data[position + 4]) << 8) |
            (static_cast<u32>(response_.data[position + 5]) << 16) |
            (static_cast<u32>(response_.data[position + 6]) << 24);
        position += list_record_header_size;
        if (name_length == 0 || name_length >= max_name ||
            name_length > response_.length - position) { return status_value(status::io); }
        entry& item = entries[count];
        for (u32 i = 0; i < name_length; ++i) {
            const u8 c = response_.data[position + i];
            if (c < 0x20 || c == 0x7f) { return status_value(status::io); }
            item.name[i] = static_cast<char>(c);
        }
        item.name[name_length] = '\0';
        if (!xos::text::valid(item.name, name_length)) { return status_value(status::io); }
        item.size = size;
        item.version = 0;
        item.directory = (attributes & entry_is_directory) != 0;
        ++count;
        position += name_length;
    }
    if (response_.value > 0xffffffffu) { return status_value(status::io); }
    cursor = static_cast<u32>(response_.value);
    return 0;
}

i64 client::set_cwd(const char* path, u64 target_pid, bool initialize_only) {
    session_guard guard;
    request_ = request{};
    if (path != nullptr) {
        u32 length = 0;
        const i64 result = set_path(path, request_.name, length);
        if (result != 0) { return result; }
        request_.name_length = length;
    }
    request_.offset = target_pid;
    request_.flags = initialize_only ? 1u : 0u;
    return call(op::cwd_set);
}

i64 client::set_cwd_handle(u32 directory_handle) {
    session_guard guard;
    if (directory_handle == 0) { return status_value(status::bad_handle); }
    request_ = request{};
    request_.handle = directory_handle;
    return call(op::cwd_set);
}

i64 client::copy_response_path(char* path, u32 capacity) {
    const u32 length = response_.name_length;
    if (length == 0 || length >= max_name || response_.name[length] != '\0' ||
        response_.name[0] != '/' || !xos::text::valid(response_.name, length)) {
        return status_value(status::io);
    }
    if (path == nullptr || capacity <= length) { return status_value(status::name_too_long); }
    for (u32 i = 0; i <= length; ++i) { path[i] = response_.name[i]; }
    return 0;
}

i64 client::get_cwd(char* path, u32 capacity) {
    session_guard guard;
    request_ = request{};
    const i64 result = call(op::cwd_get);
    return result == 0 ? copy_response_path(path, capacity) : result;
}

i64 client::resolve_path(const char* path, char* absolute, u32 capacity) {
    session_guard guard;
    request_ = request{};
    u32 length = 0;
    const i64 prepared = set_path(path, request_.name, length);
    if (prepared != 0) { return prepared; }
    request_.name_length = length;
    const i64 result = call(op::resolve_path);
    return result == 0 ? copy_response_path(absolute, capacity) : result;
}

i64 client::list(entry* entries, u32 capacity, u32& count) {
    session_guard guard;
    count = 0;
    if (entries == nullptr || capacity == 0) { return status_value(status::invalid); }
    u32 cursor = 0;
    do {
        u32 page_count = 0;
        const i64 result = list("/", entries + count, capacity - count, page_count, cursor);
        if (result != 0) { return result; }
        count += page_count;
        if (count == capacity && cursor != 0) { return status_value(status::full); }
    } while (cursor != 0);
    return 0;
}

i64 client::stat(const char* path, u32& size, u32& version) {
    session_guard guard;
    u32 attributes = 0;
    const i64 result = stat_info(path, size, attributes);
    version = 0;
    if (result != 0) { return result; }
    version = attributes;
    return 0;
}

i64 client::stat_info(const char* path, u32& size, u32& attributes) {
    session_guard guard;
    u32 identity = 0;
    return stat_info(path, size, attributes, identity);
}

i64 client::stat_info(const char* path, u32& size, u32& attributes, u32& identity) {
    u64 mtime = 0;
    return stat_info(path, size, attributes, identity, mtime);
}

i64 client::stat_info(const char* path, u32& size, u32& attributes, u32& identity,
                      u64& mtime) {
    u32 mode = 0;
    return stat_info(path, size, attributes, identity, mtime, mode);
}

i64 client::decode_metadata(u64& mtime, u32& mode) {
    mode = 0;
    mtime = 0;
    if (response_.length == 0) {
        metadata_format_ = 1;
        return 0;
    }
    if (response_.length != 24) { metadata_format_ = 0; return status_value(status::io); }
    const u8* r = response_.data;
    if (r[0] != 'F' || r[1] != 'M' || r[2] != 'E' || r[3] != 'T' ||
        r[4] != 1 || r[5] != 0 || r[6] != 24 || r[7] != 0) {
        return status_value(status::io);
    }
    u64 seconds = 0;
    for (u32 i = 0; i < 8; ++i) { seconds |= static_cast<u64>(r[8 + i]) << (8 * i); }
    u32 nanoseconds = 0;
    for (u32 i = 0; i < 4; ++i) { nanoseconds |= static_cast<u32>(r[16 + i]) << (8 * i); }
    u32 record_mode = 0;
    for (u32 i = 0; i < 4; ++i) { record_mode |= static_cast<u32>(r[20 + i]) << (8 * i); }
    if (nanoseconds >= 1000000000u) { return status_value(status::io); }
    const u32 type = record_mode & 0170000u;
    if (type != 0100000u && type != 0040000u) { return status_value(status::io); }
    metadata_format_ = 2;
    mtime = seconds;
    mode = record_mode;
    return 0;
}

i64 client::stat_info(const char* path, u32& size, u32& attributes, u32& identity,
                      u64& mtime, u32& mode) {
    session_guard guard;
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.name_length = path_length;
    const i64 result = call(op::stat);
    if (result != 0) { return result; }
    size = static_cast<u32>(response_.value);
    attributes = response_.flags;
    identity = response_.reserved;
    return decode_metadata(mtime, mode);
}

i64 client::anonymous(u32& handle) {
    session_guard guard;
    request_ = request{};
    const i64 result = call(op::anonymous);
    if (result != 0) { return result; }
    if (response_.handle == 0) { return status_value(status::io); }
    handle = response_.handle;
    return 0;
}

i64 client::seal_anonymous(u32 handle) {
    session_guard guard;
    request_ = request{};
    request_.handle = handle;
    return call(op::anonymous_seal);
}

i64 client::open(const char* path, u32 flags, u32& handle, u32& size, u32& version) {
    session_guard guard;
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.flags = flags;
    request_.name_length = path_length;
    const i64 result = call(op::open);
    if (result != 0) { return result; }
    handle = response_.handle;
    size = static_cast<u32>(response_.value);
    version = response_.flags;
    return 0;
}

i64 client::fstat(u32 handle, u32& size, u32& attributes) {
    session_guard guard;
    u32 identity = 0;
    return fstat(handle, size, attributes, identity);
}

i64 client::fstat(u32 handle, u32& size, u32& attributes, u32& identity) {
    u64 mtime = 0;
    return fstat(handle, size, attributes, identity, mtime);
}

i64 client::fstat(u32 handle, u32& size, u32& attributes, u32& identity, u64& mtime) {
    u32 mode = 0;
    return fstat(handle, size, attributes, identity, mtime, mode);
}

i64 client::fstat(u32 handle, u32& size, u32& attributes, u32& identity,
                  u64& mtime, u32& mode) {
    session_guard guard;
    request_ = request{};
    request_.handle = handle;
    const i64 result = call(op::fstat);
    if (result != 0) { return result; }
    size = static_cast<u32>(response_.value);
    attributes = response_.flags;
    identity = response_.reserved;
    return decode_metadata(mtime, mode);
}

i64 client::set_metadata(u32 handle, const char* path, u16 mask, u16 attr,
                         i64 atime_sec, i64 atime_nsec, i64 mtime_sec, i64 mtime_nsec) {
    session_guard guard;
    if ((handle == 0 && path == nullptr) || (handle != 0 && path != nullptr)) {
        return status_value(status::invalid);
    }
    request_ = request{};
    request_.handle = handle;
    request_.length = sizeof(metadata_request);
    if (path != nullptr) {
        u32 path_length = 0;
        const i64 path_result = set_path(path, request_.name, path_length);
        if (path_result != 0) { return path_result; }
        request_.name_length = path_length;
    }
    metadata_request metadata{};
    metadata.version = 1;
    metadata.mask = mask;
    metadata.attr = attr;
    metadata.atime_sec = atime_sec;
    metadata.atime_nsec = atime_nsec;
    metadata.mtime_sec = mtime_sec;
    metadata.mtime_nsec = mtime_nsec;
    for (u32 i = 0; i < sizeof(metadata); ++i) {
        request_.data[i] = reinterpret_cast<const u8*>(&metadata)[i];
    }
    return call(op::set_metadata);
}

i64 client::read(u32 handle, void* data, u32 length) {
    session_guard guard;
    if ((data == nullptr && length != 0) || length > sizeof(request_.data)) {
        return status_value(status::invalid);
    }
    request_ = request{};
    request_.handle = handle;
    request_.length = length;
    const i64 result = call(op::read);
    if (result != 0) { return result; }
    const u32 received = response_.length;
    if (received > length || received > sizeof(response_.data)) {
        return status_value(status::io);
    }
    auto* target = static_cast<u8*>(data);
    for (u32 i = 0; i < received; ++i) { target[i] = response_.data[i]; }
    return static_cast<i64>(received);
}

i64 client::write(u32 handle, const void* data, u32 length) {
    session_guard guard;
    if ((data == nullptr && length != 0) || length > sizeof(request_.data)) {
        return status_value(status::invalid);
    }
    request_ = request{};
    request_.handle = handle;
    request_.length = length;
    const auto* source = static_cast<const u8*>(data);
    for (u32 i = 0; i < length; ++i) { request_.data[i] = source[i]; }
    const i64 result = call(op::write);
    if (result != 0) { return result; }
    if (response_.value > length) { return status_value(status::io); }
    return static_cast<i64>(response_.value);
}

i64 client::seek(u32 handle, u32 offset) {
    return seek(handle, static_cast<i64>(offset), seek_set);
}

i64 client::seek(u32 handle, i64 offset, u32 origin) {
    session_guard guard;
    request_ = request{};
    request_.handle = handle;
    request_.offset = static_cast<u64>(offset);
    request_.flags = origin;
    const i64 result = call(op::seek);
    return result == 0 ? static_cast<i64>(response_.value) : result;
}

i64 client::truncate(u32 handle, u32 size) {
    session_guard guard;
    if (size > fat32_max_file_bytes) { return status_value(status::no_space); }
    request_ = request{};
    request_.handle = handle;
    request_.offset = size;
    return call(op::truncate);
}

i64 client::transfer(u32 handle, u64 target_pid, u32& target_handle) {
    session_guard guard;
    request_ = request{};
    request_.handle = handle;
    request_.offset = target_pid;
    const i64 result = call(op::transfer);
    if (result == 0) { target_handle = response_.handle; }
    return result;
}

i64 client::clone_session(u64 child_pid) {
    session_guard guard;
    request_ = request{};
    request_.offset = child_pid;
    return call(op::clone_session);
}

i64 client::close(u32 handle) {
    session_guard guard;
    request_ = request{};
    request_.handle = handle;
    return call(op::close);
}

i64 client::begin_replace(const char* path, u32 length) {
    session_guard guard;
    if (length > fat32_max_file_bytes) { return status_value(status::no_space); }
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.length = length;
    request_.name_length = path_length;
    return call(op::replace_begin);
}

i64 client::chunk_replace(u32 offset, const void* data, u32 length) {
    session_guard guard;
    if ((data == nullptr && length != 0) || length > sizeof(request_.data) ||
        offset > fat32_max_file_bytes || length > fat32_max_file_bytes - offset) {
        return status_value(status::invalid);
    }
    request_ = request{};
    request_.offset = offset;
    request_.length = length;
    const auto* source = static_cast<const u8*>(data);
    for (u32 i = 0; i < length; ++i) { request_.data[i] = source[i]; }
    return call(op::replace_chunk);
}

i64 client::commit_replace() {
    session_guard guard;
    request_ = request{};
    return call(op::replace_commit);
}

i64 client::abort_replace() {
    session_guard guard;
    request_ = request{};
    return call(op::replace_abort);
}

i64 client::replace(const char* path, const void* data, u32 length) {
    session_guard guard;
    if (data == nullptr && length != 0) { return status_value(status::invalid); }
    const i64 started = begin_replace(path, length);
    if (started != 0) { return started; }
    const auto* source = static_cast<const u8*>(data);
    u32 offset = 0;
    while (offset < length) {
        u32 chunk = length - offset;
        if (chunk > sizeof(request_.data)) { chunk = sizeof(request_.data); }
        const i64 result = chunk_replace(offset, source + offset, chunk);
        if (result != 0) { (void)abort_replace(); return result; }
        offset += chunk;
    }
    const i64 committed = commit_replace();
    if (committed != 0) { (void)abort_replace(); }
    return committed;
}

i64 client::read_all(const char* path, void* data, u32 capacity, u32& length) {
    session_guard guard;
    length = 0;
    u32 size = 0;
    u32 version = 0;
    i64 result = stat(path, size, version);
    if (result != 0) { return result; }
    if (size > capacity || (data == nullptr && size != 0)) {
        return status_value(status::no_space);
    }
    u32 handle = 0;
    u32 opened_size = 0;
    u32 opened_version = 0;
    result = open(path, read_only | open_pin, handle, opened_size, opened_version);
    if (result != 0) { return result; }
    if (opened_size != size || opened_version != version) {
        (void)close(handle);
        return status_value(status::busy);
    }
    auto* target = static_cast<u8*>(data);
    u32 position = 0;
    while (position < size) {
        const u32 wanted = size - position > sizeof(response_.data)
                               ? static_cast<u32>(sizeof(response_.data))
                               : size - position;
        const i64 got = read(handle, target + position, wanted);
        if (got <= 0 || static_cast<u64>(got) > wanted) {
            (void)close(handle);
            return status_value(status::io);
        }
        position += static_cast<u32>(got);
    }
    result = close(handle);
    if (result != 0) { return result; }
    length = position;
    return 0;
}

i64 client::remove(const char* path) {
    session_guard guard;
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.name_length = path_length;
    return call(op::remove);
}

i64 client::remove_directory(const char* path) {
    session_guard guard;
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.name_length = path_length;
    request_.flags = allow_directory;
    return call(op::remove);
}

i64 client::mkdir(const char* path) {
    session_guard guard;
    request_ = request{};
    u32 path_length = 0;
    const i64 path_result = set_path(path, request_.name, path_length);
    if (path_result != 0) { return path_result; }
    request_.name_length = path_length;
    return call(op::mkdir);
}

i64 client::rename(const char* old_path, const char* new_path) {
    session_guard guard;
    request_ = request{};
    u32 old_length = 0;
    const i64 old_result = set_path(old_path, request_.name, old_length);
    if (old_result != 0) { return old_result; }
    request_.name_length = old_length;
    u32 new_length = 0;
    const i64 new_result = set_path(new_path, reinterpret_cast<char*>(request_.data), new_length);
    if (new_result != 0 || new_length + 1 > sizeof(request_.data)) {
        return status_value(status::invalid);
    }
    request_.length = new_length;
    request_.data[new_length] = 0;
    return call(op::rename);
}

i64 client::block_bench(u32 length) {
    session_guard guard;
    if (length == 0 || length > max_block_bench_bytes) {
        return status_value(status::invalid);
    }
    request_ = request{};
    request_.length = length;
    const i64 result = call(op::block_bench);
    return result == 0 ? static_cast<i64>(response_.value) : result;
}

i64 client::sync() {
    session_guard guard;
    request_ = request{};
    return call(op::sync);
}
i64 client::maintenance_acquire() {
    session_guard guard;
    request_ = request{};
    return call(op::maintenance_acquire);
}
i64 client::maintenance_release() {
    session_guard guard;
    request_ = request{};
    return call(op::maintenance_release);
}
}
