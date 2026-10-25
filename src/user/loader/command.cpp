// SPDX-License-Identifier: Apache-2.0
#include <xos/execution.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>

namespace xos::execution {
namespace {
file::Client client;
bool client_ready;

bool file_read(void* context, u64 offset, u8* destination, u32 length) {
    auto& handle = *static_cast<u32*>(context);
    if (offset > 0xffffffffu || client.seek(handle, static_cast<u32>(offset)) < 0) {
        return false;
    }
    u32 done = 0;
    while (done < length) {
        u32 amount = length - done;
        if (amount > file::response_data_size) { amount = file::response_data_size; }
        const i64 read = client.read(handle, destination + done, amount);
        if (read <= 0 || static_cast<u64>(read) > amount) { return false; }
        done += static_cast<u32>(read);
    }
    return true;
}

candidate empty_candidate(const char* path, candidate_kind kind, i64 error = 0) {
    candidate result{};
    result.kind = kind;
    result.error = error;
    if (path != nullptr) {
        u32 i = 0;
        while (i < sizeof(result.path) - 1 && path[i] != '\0') {
            result.path[i] = path[i];
            ++i;
        }
        result.path[i] = '\0';
    }
    return result;
}

bool has_slash(const char* text) {
    if (text == nullptr) { return false; }
    for (u32 i = 0; text[i] != '\0'; ++i) { if (text[i] == '/') { return true; } }
    return false;
}

bool missing_error(i64 error) { return error == static_cast<i64>(file::status::not_found); }
}

candidate inspect(const char* path) {
    candidate result = empty_candidate(path, candidate_kind::unreadable);
    if (path == nullptr || path[0] == '\0') {
        result.error = static_cast<i64>(file::status::invalid);
        return result;
    }
    if (!client_ready) {
        if (!client.init()) { result.error = process_error_resources; return result; }
        client_ready = true;
    }
    u32 size = 0, attributes = 0;
    const i64 stated = client.stat_info(path, size, attributes);
    if (stated < 0) {
        result.error = stated;
        if (missing_error(stated)) { result.kind = candidate_kind::missing; }
        return result;
    }
    if ((attributes & file::stat_is_directory) != 0) {
        result.kind = candidate_kind::directory;
        result.error = 0;
        return result;
    }

    u32 handle = 0, opened_size = 0, version = 0;
    const i64 opened = client.open(path, file::read_only, handle, opened_size, version);
    (void)version;
    if (opened < 0) {
        result.error = opened;
        if (missing_error(opened)) { result.kind = candidate_kind::missing; }
        return result;
    }
    u32 opened_attributes = 0;
    const i64 fstat = client.fstat(handle, opened_size, opened_attributes);
    if (fstat < 0 || (opened_attributes & file::stat_is_directory) != 0) {
        result.kind = fstat == 0 ? candidate_kind::directory : candidate_kind::unreadable;
        result.error = fstat;
        const i64 closed = client.close(handle);
        if (closed < 0) {
            result.kind = candidate_kind::unreadable;
            result.error = closed;
        }
        return result;
    }

    elf::load_plan plan{};
    const elf::error inspected = elf::inspect_reader(file_read, &handle, opened_size,
                                                      sdk::target_elf_machine(), plan);
    const i64 closed = client.close(handle);
    if (inspected == elf::error::none && closed >= 0) {
        result.kind = candidate_kind::executable;
        result.error = 0;
    } else if (inspected == elf::error::io || closed < 0) {
        result.kind = candidate_kind::unreadable;
        result.error = closed < 0 ? closed : static_cast<i64>(file::status::io);
    } else {
        result.kind = inspected == elf::error::target
            ? candidate_kind::incompatible : candidate_kind::not_executable;
        result.format_error = inspected;
        result.error = static_cast<i64>(file::status::invalid);
    }
    return result;
}

candidate resolve(const char* name, const char* search_path) {
    if (name == nullptr || name[0] == '\0') {
        return empty_candidate(name, candidate_kind::missing,
                               static_cast<i64>(file::status::invalid));
    }
    if (has_slash(name)) { return inspect(name); }
    candidate first_rejected = empty_candidate(name, candidate_kind::missing,
                                               static_cast<i64>(file::status::not_found));
    if (search_path == nullptr) { return first_rejected; }
    u32 start = 0;
    while (true) {
        u32 end = start;
        while (search_path[end] != '\0' && search_path[end] != ':') { ++end; }
        const u32 dir_length = end - start;
        if (dir_length != 0) {
            bool slash = search_path[end - 1] == '/';
            u32 name_length = 0;
            while (name[name_length] != '\0') { ++name_length; }
            const u32 total = dir_length + (slash ? 0 : 1) + name_length;
            if (total < 256) {
                char path[256]{};
                u32 at = 0;
                for (; at < dir_length; ++at) { path[at] = search_path[start + at]; }
                if (!slash) { path[at++] = '/'; }
                for (u32 i = 0; i < name_length; ++i) { path[at++] = name[i]; }
                path[at] = '\0';
                candidate current = inspect(path);
                if (current.kind == candidate_kind::executable) { return current; }
                // Resource/I/O failures are not evidence to select another program.
                if (current.kind == candidate_kind::unreadable) { return current; }
                if (current.kind != candidate_kind::missing &&
                    first_rejected.kind == candidate_kind::missing) {
                    first_rejected = current;
                }
            } else if (first_rejected.kind == candidate_kind::missing) {
                first_rejected = empty_candidate(name, candidate_kind::unreadable,
                    static_cast<i64>(file::status::invalid));
            }
        }
        if (search_path[end] == '\0') { break; }
        start = end + 1;
    }
    return first_rejected;
}

const char* kind_name(candidate_kind kind) {
    switch (kind) {
    case candidate_kind::missing: return "missing";
    case candidate_kind::directory: return "directory";
    case candidate_kind::executable: return "executable";
    case candidate_kind::not_executable: return "not_executable";
    case candidate_kind::incompatible: return "incompatible";
    case candidate_kind::unreadable: return "unreadable";
    }
    return "unknown";
}
}
