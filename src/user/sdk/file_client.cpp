#include <xos/file_client.hpp>
#include <xos/sdk.hpp>

namespace xos::file {
namespace {
i64 status_value(status code) { return static_cast<i64>(code); }
}

bool Client::init() {
    send_handle_ = 0;
    recv_handle_ = 0;
    request_id_ = 0;
    return sdk::ipc_handles(send_handle_, recv_handle_) == 0 &&
           send_handle_ != 0 && recv_handle_ != 0;
}

i64 Client::call(op operation) {
    request_.magic = request_magic;
    request_.version = abi_version;
    request_.operation = static_cast<u16>(operation);
    request_.request_id = ++request_id_;
    if (sdk::ipc_send(send_handle_, &request_, sizeof(request_)) < 0) {
        return status_value(status::io);
    }
    for (u32 attempt = 0; attempt < 8192; ++attempt) {
        const i64 received = sdk::ipc_recv(recv_handle_, &response_, sizeof(response_));
        if (received == static_cast<i64>(sizeof(response_)) &&
            response_.magic == response_magic && response_.version == abi_version &&
            response_.request_id == request_.request_id) {
            return response_.status_code;
        }
        sdk::yield();
    }
    return status_value(status::would_block);
}

i64 Client::ping() {
    request_ = request{};
    return call(op::ping);
}

i64 Client::list(entry* entries, u32 capacity, u32& count) {
    count = 0;
    if (entries == nullptr || capacity == 0) { return status_value(status::invalid); }
    request_ = request{};
    const i64 result = call(op::list);
    if (result != 0) { return result; }
    u32 position = 0;
    while (position < response_.length && count < capacity) {
        entry& item = entries[count];
        u32 name_length = 0;
        while (position < response_.length && response_.data[position] != ' ' &&
               name_length + 1 < max_name) {
            item.name[name_length++] = static_cast<char>(response_.data[position++]);
        }
        item.name[name_length] = '\0';
        if (position < response_.length && response_.data[position] == ' ') { ++position; }
        u32 size = 0;
        while (position < response_.length && response_.data[position] >= '0' &&
               response_.data[position] <= '9') {
            size = size * 10 + static_cast<u32>(response_.data[position++] - '0');
        }
        if (position < response_.length && response_.data[position] == ' ') { ++position; }
        u32 version = 0;
        while (position < response_.length && response_.data[position] >= '0' &&
               response_.data[position] <= '9') {
            version = version * 10 + static_cast<u32>(response_.data[position++] - '0');
        }
        if (position < response_.length && response_.data[position] == '\n') { ++position; }
        item.size = size;
        item.version = version;
        ++count;
    }
    return 0;
}

i64 Client::stat(const char* name, u32& size, u32& version) {
    if (name == nullptr) { return status_value(status::invalid); }
    request_ = request{};
    request_.name_length = static_cast<u32>(sdk::length(name));
    for (u32 i = 0; i + 1 < max_name && name[i] != '\0'; ++i) { request_.name[i] = name[i]; }
    const i64 result = call(op::stat);
    if (result != 0) { return result; }
    size = static_cast<u32>(response_.value);
    version = response_.flags;
    return 0;
}

i64 Client::open(const char* name, u32 flags, u32& handle, u32& size, u32& version) {
    if (name == nullptr) { return status_value(status::invalid); }
    request_ = request{};
    request_.flags = flags;
    request_.name_length = static_cast<u32>(sdk::length(name));
    for (u32 i = 0; i + 1 < max_name && name[i] != '\0'; ++i) { request_.name[i] = name[i]; }
    const i64 result = call(op::open);
    if (result != 0) { return result; }
    handle = response_.handle;
    size = static_cast<u32>(response_.value);
    version = response_.flags;
    return 0;
}

i64 Client::read(u32 handle, void* data, u32 length) {
    if (data == nullptr || length > sizeof(request_.data)) { return status_value(status::invalid); }
    request_ = request{};
    request_.handle = handle;
    request_.length = length;
    const i64 result = call(op::read);
    if (result != 0) { return result; }
    const u32 received = response_.length;
    auto* target = static_cast<u8*>(data);
    for (u32 i = 0; i < received; ++i) { target[i] = response_.data[i]; }
    return static_cast<i64>(received);
}

i64 Client::write(u32 handle, const void* data, u32 length) {
    if (data == nullptr || length > sizeof(request_.data)) { return status_value(status::invalid); }
    request_ = request{};
    request_.handle = handle;
    request_.length = length;
    const auto* source = static_cast<const u8*>(data);
    for (u32 i = 0; i < length; ++i) { request_.data[i] = source[i]; }
    const i64 result = call(op::write);
    if (result != 0) { return result; }
    return static_cast<i64>(response_.value);
}

i64 Client::seek(u32 handle, u32 offset) {
    request_ = request{};
    request_.handle = handle;
    request_.offset = offset;
    const i64 result = call(op::seek);
    if (result != 0) { return result; }
    return static_cast<i64>(response_.value);
}

i64 Client::close(u32 handle) {
    request_ = request{};
    request_.handle = handle;
    return call(op::close);
}

i64 Client::begin_replace(const char* name, u32 length) {
    if (name == nullptr || length > max_file_bytes) { return status_value(status::no_space); }
    request_ = request{};
    request_.handle = 100;
    request_.reserved = static_cast<u32>(sdk::pid());
    request_.length = length;
    request_.name_length = static_cast<u32>(sdk::length(name));
    for (u32 i = 0; i + 1 < max_name && name[i] != '\0'; ++i) { request_.name[i] = name[i]; }
    const i64 result = call(op::replace_begin);
    return result;
}

i64 Client::abort_replace() {
    request_ = request{};
    request_.handle = 100;
    request_.reserved = static_cast<u32>(sdk::pid());
    return call(op::replace_abort);
}

i64 Client::replace(const char* name, const void* data, u32 length) {
    const i64 started = begin_replace(name, length);
    if (started != 0) { return started; }
    const auto* source = static_cast<const u8*>(data);
    u32 offset = 0;
    while (offset < length) {
        u32 chunk = length - offset;
        if (chunk > sizeof(request_.data)) { chunk = sizeof(request_.data); }
        request_ = request{};
        request_.handle = 100;
        request_.reserved = static_cast<u32>(sdk::pid());
        request_.offset = offset;
        request_.length = chunk;
        for (u32 i = 0; i < chunk; ++i) { request_.data[i] = source[offset + i]; }
        const i64 result = call(op::replace_chunk);
        if (result != 0) { (void)abort_replace(); return result; }
        offset += chunk;
    }
    request_ = request{};
    request_.handle = 100;
    request_.reserved = static_cast<u32>(sdk::pid());
    const i64 committed = call(op::replace_commit);
    if (committed != 0) { (void)abort_replace(); return committed; }
    return 0;
}

i64 Client::read_all(const char* name, void* data, u32 capacity, u32& length) {
    length = 0;
    u32 size = 0;
    u32 version = 0;
    i64 result = stat(name, size, version);
    if (result != 0) { return result; }
    if (size > capacity) { return status_value(status::no_space); }
    u32 handle = 0;
    u32 opened_size = 0;
    u32 opened_version = 0;
    result = open(name, read_only, handle, opened_size, opened_version);
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
        if (got <= 0) { (void)close(handle); return status_value(status::io); }
        position += static_cast<u32>(got);
    }
    result = close(handle);
    if (result != 0) { return result; }
    length = position;
    return 0;
}

i64 Client::sync() {
    request_ = request{};
    return call(op::sync);
}

i64 Client::remove(const char* name) {
    if (name == nullptr) { return status_value(status::invalid); }
    request_ = request{};
    request_.name_length = static_cast<u32>(sdk::length(name));
    for (u32 i = 0; i + 1 < max_name && name[i] != '\0'; ++i) { request_.name[i] = name[i]; }
    return call(op::remove);
}
}
