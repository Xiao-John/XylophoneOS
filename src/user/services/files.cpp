// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>
#include <xos/text.hpp>
#include <stddef.h>
#include "ff.h"
#include "diskio.h"

namespace {
using namespace xos;
using namespace xos::file;

constexpr char temp_name[] = "XOSTMP.TMP";
constexpr char backup_name[] = "XOSBAK.TMP";
constexpr char journal_name[] = "XOSJRNL.TMP";
constexpr u32 disk_slack_clusters = 2;
// Eight-character FAT names avoid a second, unreserved short-name alias.
constexpr u32 anonymous_serial_limit = 100000;
constexpr u32 anonymous_collision_limit = 128;
u32 next_anonymous_serial;

struct open_record {
    bool used;
    u32 handle;
    u32 description;
};

struct open_description {
    bool used;
    bool anonymous;
    bool closed;
    u32 references;
    FIL file;
    char path[max_name];
    u32 flags;
};

struct client_session {
    u64 pid;
    u32 request_handle;
    u32 response_handle;
    open_record opens[max_open];
};

FATFS fs;
bool mounted;
bool recovery_failed;
u64 maintenance_writer;
client_session sessions[max_sessions];
u32 generations[max_sessions];
open_description descriptions[max_open_descriptions];
request request_buffer;
response response_buffer;
u8 block_bench_buffer[4096];
FIL staging_file;
bool staging_active;
bool staging_open;
char staging_path[max_name];
u64 staging_owner;
u32 staging_written;
u32 staging_total;

struct file_identity_key {
    u32 sector;
    u16 offset;
    u16 inode;
};

// Inode 1 is the volume root. Other identities are issued monotonically and
// never reused during this service lifetime, so removed entries cannot alias a
// later file. Once the 16-bit namespace is exhausted, identity queries fail.
constexpr u32 max_file_identities = 65534;
file_identity_key file_identities[max_file_identities];
u32 file_identity_count;
u32 next_file_inode = 2;

bool same_identity_key(const file_identity_key& left, const file_identity_key& right) {
    return left.sector == right.sector && left.offset == right.offset;
}

file_identity_key identity_key(const FILINFO& info) {
    return file_identity_key{info.xos_dir_sector, info.xos_dir_offset, 0};
}

file_identity_key identity_key(const FIL& file) {
    if (file.dir_ptr == nullptr || file.obj.fs == nullptr) { return file_identity_key{}; }
    const ptrdiff_t offset = file.dir_ptr - file.obj.fs->win;
    if (offset < 0 || offset >= FF_MAX_SS) { return file_identity_key{}; }
    return file_identity_key{static_cast<u32>(file.dir_sect), static_cast<u16>(offset), 0};
}

bool can_allocate_identity() {
    return file_identity_count < max_file_identities && next_file_inode <= 0xffffu;
}

bool identity_for_key(file_identity_key key, u16& inode) {
    if (key.sector == 0) { return false; }
    for (u32 i = 0; i < file_identity_count; ++i) {
        if (same_identity_key(file_identities[i], key)) {
            inode = file_identities[i].inode;
            return true;
        }
    }
    if (!can_allocate_identity()) { return false; }
    inode = static_cast<u16>(next_file_inode++);
    key.inode = inode;
    file_identities[file_identity_count++] = key;
    return true;
}

bool identity_for_info(const FILINFO& info, u16& inode) {
    return identity_for_key(identity_key(info), inode);
}

bool identity_for_file(const FIL& file, u16& inode) {
    return identity_for_key(identity_key(file), inode);
}

bool forget_identity(file_identity_key key) {
    for (u32 i = 0; i < file_identity_count; ++i) {
        if (same_identity_key(file_identities[i], key)) {
            file_identities[i] = file_identities[--file_identity_count];
            return true;
        }
    }
    return false;
}

bool move_identity(file_identity_key old_key, file_identity_key new_key, u16 inode) {
    if (new_key.sector == 0) { return false; }
    for (u32 i = 0; i < file_identity_count; ++i) {
        if (file_identities[i].inode == inode && same_identity_key(file_identities[i], old_key)) {
            file_identities[i].sector = new_key.sector;
            file_identities[i].offset = new_key.offset;
            return true;
        }
    }
    return false;
}

u32 text_length(const char* text, u32 limit) {
    u32 length = 0;
    while (length < limit && text[length] != '\0') { ++length; }
    return length;
}

void copy_text(char* destination, const char* source) {
    const u32 length = text_length(source, max_name - 1);
    for (u32 i = 0; i <= length; ++i) { destination[i] = source[i]; }
}

char upper(char value) {
    return value >= 'a' && value <= 'z' ? static_cast<char>(value - 'a' + 'A') : value;
}

bool names_equal(const char* left, const char* right) {
    u32 i = 0;
    while (left[i] != '\0' && right[i] != '\0') {
        if (upper(left[i]) != upper(right[i])) { return false; }
        ++i;
    }
    return left[i] == '\0' && right[i] == '\0';
}

// FAT long names and generated short aliases can identify the same entry.
bool same_path_object(const char* left, const char* right) {
    if (names_equal(left, right)) { return true; }
    FILINFO a{}, b{};
    const FRESULT ar = f_stat(left, &a), br = f_stat(right, &b);
    if ((ar != FR_OK && ar != FR_NO_FILE && ar != FR_NO_PATH) ||
        (br != FR_OK && br != FR_NO_FILE && br != FR_NO_PATH)) { return true; }
    if (ar != FR_OK || br != FR_OK) { return false; }
    const auto ak = identity_key(a), bk = identity_key(b);
    return ak.sector != 0 && same_identity_key(ak, bk);
}

bool reserved_component(const char* begin, u32 length) {
    // Match the namespace already reserved by the offline disk-transfer API.
    // It includes anonymous backing names and denies normal path operations.
    if (length >= 7 && upper(begin[0]) == 'X' && upper(begin[1]) == 'O' &&
        upper(begin[2]) == 'S' && begin[length - 4] == '.' &&
        upper(begin[length - 3]) == 'T' && upper(begin[length - 2]) == 'M' &&
        upper(begin[length - 1]) == 'P') { return true; }
    const char* reserved[] = {temp_name, backup_name, journal_name};
    for (const char* name : reserved) {
        u32 i = 0;
        while (i < length && name[i] != '\0' && upper(begin[i]) == upper(name[i])) { ++i; }
        if (i == length && name[i] == '\0') { return true; }
    }
    return false;
}

// Protocol paths are validated UTF-8; FatFs stores long names as UTF-16.
bool normalize_path(const char* source, u32 source_length, char* output,
                    bool allow_root, bool allow_trailing_slash = false) {
    if (source_length == 0 || source_length >= max_name) { return false; }
    if (!xos::text::valid(source, source_length)) { return false; }
    for (u32 i = 0; i < source_length; ++i) {
        const u8 c = static_cast<u8>(source[i]);
        if (c < 0x20 || c == 0x7f || c == '\\' || c == ':' || c == '*' || c == '?' ||
            c == '"' || c == '<' || c == '>' || c == '|') { return false; }
    }
    if (source[source_length - 1] == '/' && !allow_trailing_slash &&
        !(allow_root && source_length == 1)) { return false; }
    u32 begin = source[0] == '/' ? 1 : 0;
    u32 end = source_length;
    if (allow_trailing_slash && end > begin && source[end - 1] == '/') { --end; }
    if (begin == end) {
        if (!allow_root) { return false; }
        output[0] = '\0';
        return true;
    }
    u32 out = 0;
    while (begin < end) {
        u32 component_end = begin;
        while (component_end < end && source[component_end] != '/') { ++component_end; }
        const u32 length = component_end - begin;
        if (length == 0 || (length == 1 && source[begin] == '.') ||
            (length == 2 && source[begin] == '.' && source[begin + 1] == '.') ||
            source[component_end - 1] == '.' || source[component_end - 1] == ' ' ||
            reserved_component(source + begin, length)) { return false; }
        if (out != 0) { output[out++] = '/'; }
        for (u32 i = begin; i < component_end; ++i) { output[out++] = source[i]; }
        if (out >= max_name) { return false; }
        begin = component_end + 1;
    }
    if (out == 0 || out >= max_name) { return false; }
    output[out] = '\0';
    return true;
}

bool request_path(const request& in, char* output, bool allow_root = false,
                  bool allow_trailing_slash = false) {
    if (in.name_length == 0 || in.name_length >= max_name) { return false; }
    for (u32 i = 0; i < in.name_length; ++i) {
        if (in.name[i] == '\0') { return false; }
    }
    return normalize_path(in.name, in.name_length, output, allow_root, allow_trailing_slash);
}

status from_fr(FRESULT result) {
    switch (result) {
    case FR_OK: return status::ok;
    case FR_NO_FILE:
    case FR_NO_PATH:
    case FR_INVALID_NAME: return status::not_found;
    case FR_TOO_MANY_OPEN_FILES: return status::full;
    case FR_LOCKED: return status::busy;
    case FR_EXIST: return status::exists;
    case FR_DENIED:
    case FR_WRITE_PROTECTED:
    case FR_INVALID_OBJECT: return status::invalid;
    case FR_NOT_ENOUGH_CORE:
    case FR_MKFS_ABORTED: return status::no_space;
    default: return status::io;
    }
}

bool any_open(const client_session&, const char* path) {
    FILINFO info{};
    const FRESULT result = f_stat(path, &info);
    if (result != FR_OK && result != FR_NO_FILE && result != FR_NO_PATH) { return true; }
    const bool found = result == FR_OK;
    const file_identity_key key = found ? identity_key(info) : file_identity_key{};
    for (const auto& item : descriptions) {
        if (item.used && (names_equal(item.path, path) ||
            (found && key.sector != 0 && same_identity_key(key, identity_key(item.file))))) { return true; }
    }
    return false;
}

open_description* description_for(open_record* item) {
    if (item == nullptr || item->description == 0 ||
        item->description > max_open_descriptions) { return nullptr; }
    open_description& description = descriptions[item->description - 1];
    return description.used ? &description : nullptr;
}

bool anonymous_path(const char* path) {
    if (text_length(path, max_name) != 12 || path[0] != 'X' || path[1] != 'O' ||
        path[2] != 'S' || !names_equal(path + 8, ".TMP")) { return false; }
    for (u32 index = 3; index < 8; ++index) {
        if (path[index] < '0' || path[index] > '9') { return false; }
    }
    return true;
}

status cleanup_description(open_description& description) {
    // A failed close/unlink remains an owned, zero-reference description so a
    // later service sweep can retry. Never reuse its FIL or forget its path.
    if (!description.used || description.references != 0) { return status::invalid; }
    if (description.anonymous && !anonymous_path(description.path)) { return status::io; }
    file_identity_key identity{};
    // FatFs keeps dir_sect/dir_ptr after f_close invalidates obj.fs. The volume
    // and its window are permanent, so pending unlink retains the same key.
    if (description.file.dir_ptr != nullptr) {
        const ptrdiff_t offset = description.file.dir_ptr - fs.win;
        if (offset >= 0 && offset < FF_MAX_SS) {
            identity = {static_cast<u32>(description.file.dir_sect), static_cast<u16>(offset), 0};
        }
    }
    if (!description.closed) {
        const FRESULT result = f_close(&description.file);
        if (result != FR_OK) { return from_fr(result); }
        description.closed = true;
    }
    if (description.anonymous) {
        const FRESULT result = f_unlink(description.path);
        if (result != FR_OK && result != FR_NO_FILE && result != FR_NO_PATH) { return from_fr(result); }
        (void)forget_identity(identity);
    }
    description = open_description{};
    return status::ok;
}

status release_open(open_record& item) {
    open_description* description = description_for(&item);
    status result = status::ok;
    if (description != nullptr) {
        if (description->references > 1) { --description->references; }
        else {
            description->references = 0;
            result = cleanup_description(*description);
        }
    }
    item = open_record{};
    return result;
}

void retry_description_cleanup() {
    for (auto& description : descriptions) {
        if (description.used && description.references == 0) { (void)cleanup_description(description); }
    }
}

void close_session(client_session& session) {
    for (auto& item : session.opens) {
        if (item.used) { release_open(item); }
    }
    if (staging_active && staging_owner == session.pid) {
        if (staging_open) { if (f_close(&staging_file) != FR_OK) { recovery_failed = true; } staging_open = false; }
        const FRESULT removed = f_unlink(temp_name);
        if (removed != FR_OK && removed != FR_NO_FILE && removed != FR_NO_PATH) { recovery_failed = true; }
        staging_active = false;
        staging_owner = 0;
        staging_written = 0;
        staging_total = 0;
        staging_path[0] = '\0';
    }
}

bool remove_if_present(const char* path) {
    FILINFO info{};
    const FRESULT result = f_stat(path, &info);
    if (result == FR_NO_FILE || result == FR_NO_PATH) { return true; }
    return result == FR_OK && f_unlink(path) == FR_OK;
}

bool write_journal(const char* path) {
    FIL file{};
    if (f_open(&file, journal_name, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK) { return false; }
    const UINT length = static_cast<UINT>(text_length(path, max_name) + 1);
    UINT written = 0;
    FRESULT result = f_write(&file, path, length, &written);
    if (result == FR_OK) { result = f_sync(&file); }
    const FRESULT closed = f_close(&file);
    return result == FR_OK && closed == FR_OK && written == length;
}

bool read_journal(char* path) {
    FIL file{};
    if (f_open(&file, journal_name, FA_READ) != FR_OK) { return false; }
    UINT read = 0;
    const FRESULT result = f_read(&file, path, max_name, &read);
    const FRESULT closed = f_close(&file);
    if (result != FR_OK || closed != FR_OK || read < 2 || read > max_name || path[read - 1] != '\0') { return false; }
    return normalize_path(path, read - 1, path, false);
}

bool missing(FRESULT result) { return result == FR_NO_FILE || result == FR_NO_PATH; }

// Keep the journal through cleanup and its flush. On an ambiguous final delete/
// flush error, try to restore the marker; never reopen the service after failure.
bool finish_recovery(const char* path) {
    if (disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK ||
        !remove_if_present(temp_name) || !remove_if_present(backup_name) ||
        disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) { return false; }
    if (f_unlink(journal_name) != FR_OK) { return false; }
    if (disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
        (void)write_journal(path); // deleted marker: best effort; caller stays failed closed
        return false;
    }
    return true;
}

void recover() {
    FILINFO journal_info{};
    const FRESULT journal_result = f_stat(journal_name, &journal_info);
    if (missing(journal_result)) {
        if (!remove_if_present(temp_name) || disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
            recovery_failed = true;
        }
        return;
    }
    if (journal_result != FR_OK || (journal_info.fattrib & AM_DIR) != 0 ||
        journal_info.fsize < 2 || journal_info.fsize > max_name) {
        recovery_failed = true; return;
    }
    char path[max_name]{};
    if (!read_journal(path)) { recovery_failed = true; return; }
    FILINFO target_info{}, backup_info{}, temp_info{};
    const FRESULT target_result = f_stat(path, &target_info);
    const FRESULT backup_result = f_stat(backup_name, &backup_info);
    const FRESULT temp_result = f_stat(temp_name, &temp_info);
    // Complete all existence/type checks before removing any recovery material.
    if ((target_result != FR_OK && !missing(target_result)) ||
        (backup_result != FR_OK && !missing(backup_result)) ||
        (temp_result != FR_OK && !missing(temp_result)) ||
        (target_result == FR_OK && (target_info.fattrib & AM_DIR) != 0) ||
        (backup_result == FR_OK && (backup_info.fattrib & AM_DIR) != 0) ||
        (temp_result == FR_OK && (temp_info.fattrib & AM_DIR) != 0)) {
        recovery_failed = true; return;
    }
    if (backup_result == FR_OK && missing(target_result) && f_rename(backup_name, path) != FR_OK) {
        recovery_failed = true; return;
    }
    if (!finish_recovery(path)) { recovery_failed = true; }
}

void reply(response& out, const request& in, status code) {
    out = response{};
    out.magic = response_magic;
    out.version = abi_version;
    out.status_code = static_cast<i32>(code);
    out.request_id = in.request_id;
}

bool supported_name(const char* name, u32& length) {
    length = text_length(name, max_name);
    if (length == 0 || length >= max_name) { return false; }
    if (!xos::text::valid(name, length)) { return false; }
    for (u32 i = 0; i < length; ++i) {
        const u8 c = static_cast<u8>(name[i]);
        if (c < 0x20 || c == 0x7f) { return false; }
    }
    return true;
}

void list_directory(const request& in, response& out) {
    char path[max_name]{};
    if (!request_path(in, path, true, true)) { reply(out, in, status::invalid); return; }
    DIR dir{};
    const FRESULT opened = f_opendir(&dir, path);
    if (opened != FR_OK) { reply(out, in, from_fr(opened)); return; }
    reply(out, in, status::ok);
    const u32 wanted = in.length == 0 ? 64 : in.length;
    u64 raw_index = 0;
    u32 used = 0;
    u32 emitted = 0;
    bool stopped = false;
    FILINFO info{};
    while (true) {
        const FRESULT result = f_readdir(&dir, &info);
        if (result != FR_OK) { out.status_code = static_cast<i32>(from_fr(result)); break; }
        if (info.fname[0] == '\0') { break; }
        const u64 current = raw_index++;
        if (current < in.offset) { continue; }
        u32 name_length = 0;
        if (!supported_name(info.fname, name_length)) { continue; }
        if (path[0] == '\0' && reserved_component(info.fname, name_length)) { continue; }
        const u32 record_size = list_record_header_size + name_length;
        if (emitted >= wanted || record_size > sizeof(out.data) - used) {
            out.value = current;
            stopped = true;
            break;
        }
        out.data[used++] = static_cast<u8>(name_length);
        out.data[used++] = static_cast<u8>(name_length >> 8);
        out.data[used++] = (info.fattrib & AM_DIR) != 0 ? entry_is_directory : 0;
        const u32 size = static_cast<u32>(info.fsize);
        for (u32 shift = 0; shift < 32; shift += 8) { out.data[used++] = static_cast<u8>(size >> shift); }
        for (u32 i = 0; i < name_length; ++i) { out.data[used++] = static_cast<u8>(info.fname[i]); }
        ++emitted;
    }
    if (!stopped && out.value == 0) { out.value = 0; }
    out.length = used;
    (void)f_closedir(&dir);
}

bool next_handle(u32 session_index, u32& value) {
    if (generations[session_index] == 0xffffffffu) { return false; }
    value = ++generations[session_index];
    return value != 0;
}

open_record* find_open(client_session& session, u32 handle) {
    if (handle == 0) { return nullptr; }
    for (auto& item : session.opens) {
        if (item.used && item.handle == handle) { return &item; }
    }
    return nullptr;
}

status clone_session(client_session& source, u64 child_pid) {
    // A caller-supplied PID is not transfer authority. The kernel authenticates
    // the source and its still-unstarted fork child at both transaction ends.
    const u64 source_pid = source.pid;
    if (child_pid == 0 || child_pid == source_pid ||
        sdk::syscall(sys_process_fork_files, child_pid, source_pid, 0) != 0) {
        return status::bad_handle;
    }
    client_session* target = nullptr;
    file_session_info child_info{};
    u32 target_index = max_sessions;
    for (u32 index = 0; index < max_sessions; ++index) {
        file_session_info info{};
        if (sdk::syscall(sys_file_session, index, reinterpret_cast<u64>(&info)) != 0) {
            return status::io;
        }
        if (info.pid == child_pid) {
            target = &sessions[index]; target_index = index; child_info = info; break;
        }
    }
    if (target == nullptr) { return status::would_block; }
    // A reused slot may still cache an old session. Let the ordinary session
    // sweep reclaim it (including any old staging owner); never close another
    // session as a side effect of a clone request.
    if (target->pid != 0 && target->pid != child_pid) { return status::would_block; }
    for (const auto& item : target->opens) {
        if (item.used) { return status::busy; }
    }
    u32 additions[max_open_descriptions]{};
    for (auto& item : source.opens) {
        if (!item.used) { continue; }
        open_description* description = description_for(&item);
        if (item.handle == 0 || description == nullptr || description->references == 0) {
            return status::io;
        }
        ++additions[item.description - 1];
    }
    for (u32 index = 0; index < max_open_descriptions; ++index) {
        if (additions[index] > 0xffffffffu - descriptions[index].references) { return status::full; }
    }
    target->pid = child_pid;
    target->request_handle = child_info.request_handle;
    target->response_handle = child_info.response_handle;
    for (u32 index = 0; index < max_open; ++index) {
        if (!source.opens[index].used) { continue; }
        target->opens[index] = source.opens[index];
        ++descriptions[source.opens[index].description - 1].references;
    }
    const u32 source_index = static_cast<u32>(&source - sessions);
    if (generations[target_index] < generations[source_index]) {
        generations[target_index] = generations[source_index];
    }
    // The service is single threaded: no other request or session sweep can
    // change either opens[] while we are preempted. A source kill or target
    // abort can still invalidate the kernel identity, so ACK revalidates it.
    // On failure, release only references installed in the empty target here.
    if (sdk::syscall(sys_process_fork_files, child_pid, source_pid, 1) != 0) {
        for (auto& item : target->opens) {
            if (item.used) { release_open(item); }
        }
        return status::bad_handle;
    }
    // Staging transactions retain their original owner and are not inherited.
    return status::ok;
}

void abort_staging() {
    if (staging_open) { if (f_close(&staging_file) != FR_OK) { recovery_failed = true; } staging_open = false; }
    if (!remove_if_present(temp_name)) { recovery_failed = true; }
    staging_active = false;
    staging_owner = 0;
    staging_written = 0;
    staging_total = 0;
    staging_path[0] = '\0';
}

u64 available_bytes() {
    DWORD free_clusters = 0;
    FATFS* mounted_fs = nullptr;
    if (f_getfree("", &free_clusters, &mounted_fs) != FR_OK || mounted_fs == nullptr) { return 0; }
    return static_cast<u64>(free_clusters) * mounted_fs->csize * 512u;
}

u64 required_staging_bytes(u32 bytes) {
    const u64 cluster_bytes = static_cast<u64>(fs.csize) * 512u;
    const u64 content_clusters = bytes == 0 ? 0 : (static_cast<u64>(bytes) + cluster_bytes - 1) / cluster_bytes;
    return (content_clusters + disk_slack_clusters) * cluster_bytes;
}

void handle(const request& in, response& out, client_session& session, u32 session_index) {
    if (in.magic != request_magic || in.version != abi_version) {
        reply(out, in, status::invalid);
        return;
    }
    const op operation = static_cast<op>(in.operation);
    if (operation == op::ping) {
        reply(out, in, mounted && !recovery_failed ? status::ok : status::io);
        return;
    }
    if (operation == op::block_bench) {
        if (in.length == 0 || in.length > max_block_bench_bytes) {
            reply(out, in, status::invalid);
            return;
        }
        u64 sectors_available = 0;
        if (sdk::syscall(sys_block_info, reinterpret_cast<u64>(&sectors_available)) != 0) {
            reply(out, in, status::io);
            return;
        }
        u32 remaining = (in.length + 511u) / 512u;
        if (static_cast<u64>(remaining) > sectors_available) {
            reply(out, in, status::no_space);
            return;
        }
        u64 sector = 0;
        while (remaining != 0) {
            const u32 count = remaining > 8 ? 8 : remaining;
            const i64 read = sdk::syscall(sys_block_read, sector,
                                          reinterpret_cast<u64>(block_bench_buffer), count);
            if (read != 0) { reply(out, in, status::io); return; }
            sector += count;
            remaining -= count;
            sdk::yield();
        }
        reply(out, in, status::ok);
        out.value = in.length;
        return;
    }
    if (!mounted || recovery_failed) { reply(out, in, status::io); return; }
    process_guard_info gate{};
    if (sdk::syscall(sys_process_guard, static_cast<u64>(process_guard_action::query),
                     reinterpret_cast<u64>(&gate)) != 0) { reply(out, in, status::io); return; }
    if (operation == op::maintenance_acquire) {
        if (gate.owner_pid == 0 || gate.worker_pid != session.pid || maintenance_writer != 0 || staging_active) {
            reply(out, in, status::busy); return;
        }
        for (const auto& description : descriptions) {
            if (description.used) { reply(out, in, status::busy); return; }
        }
        maintenance_writer = session.pid;
        reply(out, in, status::ok); return;
    }
    if (operation == op::maintenance_release) {
        if (gate.owner_pid != session.pid) { reply(out, in, status::invalid); return; }
        // Dead sessions are swept by the service loop. Do not release while
        // their handles or an unfinished single-file replacement remain open.
        if (staging_active) { reply(out, in, status::busy); return; }
        for (const auto& description : descriptions) {
            if (description.used) { reply(out, in, status::busy); return; }
        }
        if (sdk::syscall(sys_block_sync) != 0) { reply(out, in, status::io); return; }
        maintenance_writer = 0;
        reply(out, in, status::ok); return;
    }
    const bool mutating = operation == op::anonymous || operation == op::anonymous_seal ||
        operation == op::clone_session || operation == op::write || operation == op::replace_begin ||
        operation == op::replace_chunk || operation == op::replace_commit || operation == op::replace_abort ||
        operation == op::remove || operation == op::mkdir || operation == op::rename || operation == op::sync ||
        operation == op::truncate ||
        (operation == op::open && ((in.flags & open_access_mask) != read_only ||
                                  (in.flags & open_option_mask) != 0));
    if (mutating && (gate.owner_pid != 0 || maintenance_writer != 0) &&
        (gate.owner_pid == 0 || gate.worker_pid != session.pid || maintenance_writer != session.pid)) {
        reply(out, in, status::busy); return;
    }
    switch (operation) {
    case op::list:
        list_directory(in, out);
        break;
    case op::stat: {
        char path[max_name]{};
        if (!request_path(in, path, true)) { reply(out, in, status::invalid); break; }
        if (path[0] == '\0') {
            reply(out, in, status::ok);
            out.flags = stat_is_directory;
            out.reserved = 1;
            break;
        }
        FILINFO info{};
        const FRESULT result = f_stat(path, &info);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        u16 inode = 0;
        if (!identity_for_info(info, inode)) { reply(out, in, status::full); break; }
        reply(out, in, status::ok);
        out.value = info.fsize;
        out.reserved = inode;
        if ((info.fattrib & AM_DIR) != 0) { out.flags = stat_is_directory; }
        break;
    }
    case op::anonymous: {
        bool empty = in.handle == 0 && in.flags == 0 && in.reserved == 0 && in.offset == 0 &&
            in.length == 0 && in.name_length == 0;
        for (char byte : in.name) { empty = empty && byte == 0; }
        for (u8 byte : in.data) { empty = empty && byte == 0; }
        if (!empty) { reply(out, in, status::invalid); break; }
        u32 slot = max_open, description_slot = max_open_descriptions;
        for (u32 i = 0; i < max_open; ++i) { if (!session.opens[i].used) { slot = i; break; } }
        for (u32 i = 0; i < max_open_descriptions; ++i) {
            if (!descriptions[i].used) { description_slot = i; break; }
        }
        u32 handle = 0;
        if (slot == max_open || description_slot == max_open_descriptions ||
            next_anonymous_serial >= anonymous_serial_limit || !next_handle(session_index, handle)) {
            reply(out, in, status::full); break;
        }
        open_description& description = descriptions[description_slot];
        description = open_description{};
        FRESULT opened = FR_EXIST;
        char path[] = "XOS00000.TMP";
        for (u32 attempt = 0; attempt < anonymous_collision_limit &&
             next_anonymous_serial < anonymous_serial_limit; ++attempt) {
            u32 serial = next_anonymous_serial++;
            for (u32 digit = 0; digit < 5; ++digit) {
                path[7 - digit] = static_cast<char>('0' + serial % 10); serial /= 10;
            }
            opened = f_open(&description.file, path, FA_CREATE_NEW | FA_READ | FA_WRITE);
            if (opened != FR_EXIST) { break; }
        }
        if (opened != FR_OK) {
            // CREATE_NEW never overwrites a collision. An error does not prove
            // ownership of a pre-existing path, so do not unlink it here.
            description = open_description{};
            reply(out, in, from_fr(opened)); break;
        }
        description.used = true;
        description.anonymous = true;
        description.references = 1;
        description.flags = read_write;
        copy_text(description.path, path);
        session.opens[slot] = open_record{true, handle, description_slot + 1};
        reply(out, in, status::ok);
        out.handle = handle;
        break;
    }
    case op::anonymous_seal: {
        bool empty = in.flags == 0 && in.reserved == 0 && in.offset == 0 &&
            in.length == 0 && in.name_length == 0;
        for (char byte : in.name) { empty = empty && byte == 0; }
        for (u8 byte : in.data) { empty = empty && byte == 0; }
        if (!empty) { reply(out, in, status::invalid); break; }
        open_description* description = description_for(find_open(session, in.handle));
        if (description == nullptr || !description->anonymous || description->closed ||
            description->references == 0) { reply(out, in, status::bad_handle); break; }
        // The one description is shared by all fork/transfer references. Seal
        // only removes write authority; no FIL close/reopen or seek occurs.
        description->flags = read_only;
        reply(out, in, status::ok);
        break;
    }
    case op::open: {
        char path[max_name]{};
        const u32 access = in.flags & open_access_mask;
        const u32 options = in.flags & open_option_mask;
        if (!request_path(in, path) || (in.flags & ~open_valid_mask) != 0 ||
            (access != read_only && access != write_only && access != read_write) ||
            ((options & open_exclusive) != 0 && (options & open_create) == 0) ||
            ((options & (open_truncate | open_append)) != 0 && (access & write_only) == 0)) {
            reply(out, in, status::invalid); break;
        }
        u32 slot = max_open;
        for (u32 i = 0; i < max_open; ++i) { if (!session.opens[i].used) { slot = i; break; } }
        if (slot == max_open) { reply(out, in, status::full); break; }
        u32 description_slot = max_open_descriptions;
        for (u32 i = 0; i < max_open_descriptions; ++i) {
            if (!descriptions[i].used) { description_slot = i; break; }
        }
        if (description_slot == max_open_descriptions) { reply(out, in, status::full); break; }
        FILINFO info{};
        const FRESULT stat_result = f_stat(path, &info);
        if (stat_result == FR_OK && (info.fattrib & AM_DIR) != 0) {
            reply(out, in, status::invalid); break;
        }
        if (stat_result != FR_OK && stat_result != FR_NO_FILE) {
            reply(out, in, from_fr(stat_result)); break;
        }
        u32 handle = 0;
        if (!next_handle(session_index, handle)) { reply(out, in, status::full); break; }
        BYTE mode = FA_OPEN_EXISTING;
        if ((access & read_only) != 0) { mode |= FA_READ; }
        if ((access & write_only) != 0) { mode |= FA_WRITE; }
        if ((options & open_exclusive) != 0) { mode |= FA_CREATE_NEW; }
        else if ((options & open_truncate) != 0) { mode |= FA_CREATE_ALWAYS; }
        else if ((options & open_append) != 0) { mode |= FA_OPEN_APPEND; }
        else if ((options & open_create) != 0) { mode |= FA_OPEN_ALWAYS; }
        open_description& description = descriptions[description_slot];
        description = open_description{};
        const FRESULT result = f_open(&description.file, path, mode);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        if ((options & open_append) != 0) {
            const FRESULT seek_result = f_lseek(&description.file, f_size(&description.file));
            if (seek_result != FR_OK) {
                (void)f_close(&description.file);
                description = open_description{};
                reply(out, in, from_fr(seek_result));
                break;
            }
        }
        description.used = true;
        description.references = 1;
        description.flags = in.flags;
        copy_text(description.path, path);
        open_record& item = session.opens[slot];
        item = open_record{};
        item.used = true;
        item.handle = handle;
        item.description = description_slot + 1;
        reply(out, in, status::ok);
        out.handle = item.handle;
        out.value = f_size(&description.file);
        break;
    }
    case op::fstat: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        u16 inode = 0;
        if (!identity_for_file(description->file, inode)) { reply(out, in, status::full); break; }
        reply(out, in, status::ok);
        out.value = f_size(&description->file);
        out.reserved = inode;
        break;
    }
    case op::read: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if ((description->flags & read_only) == 0) { reply(out, in, status::invalid); break; }
        const UINT wanted = in.length > sizeof(out.data)
                                ? static_cast<UINT>(sizeof(out.data))
                                : static_cast<UINT>(in.length);
        reply(out, in, status::ok);
        UINT read = 0;
        const FRESULT result = f_read(&description->file, out.data, wanted, &read);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        out.length = read;
        out.value = read;
        break;
    }
    case op::write: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if ((description->flags & write_only) == 0) { reply(out, in, status::invalid); break; }
        if ((description->flags & open_append) != 0) {
            const FRESULT seek_result = f_lseek(&description->file, f_size(&description->file));
            if (seek_result != FR_OK) { reply(out, in, from_fr(seek_result)); break; }
        }
        const FSIZE_t position = f_tell(&description->file);
        if (position > fat32_max_file_bytes || in.length > sizeof(in.data) ||
            in.length > fat32_max_file_bytes - position) { reply(out, in, status::no_space); break; }
        UINT written = 0;
        const FRESULT result = f_write(&description->file, in.data, in.length, &written);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        reply(out, in, status::ok);
        out.value = written;
        break;
    }
    case op::seek: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        const i64 displacement = static_cast<i64>(in.offset);
        i64 base = 0;
        if (in.flags == seek_current) { base = static_cast<i64>(f_tell(&description->file)); }
        else if (in.flags == seek_end) { base = static_cast<i64>(f_size(&description->file)); }
        else if (in.flags != seek_set) { reply(out, in, status::invalid); break; }
        if ((displacement < 0 && displacement < -base) ||
            (displacement > 0 && base > static_cast<i64>(fat32_max_file_bytes) - displacement)) {
            reply(out, in, status::invalid); break;
        }
        const i64 target = base + displacement;
        if (target < 0 || target > fat32_max_file_bytes) { reply(out, in, status::invalid); break; }
        const FRESULT result = f_lseek(&description->file, static_cast<FSIZE_t>(target));
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        reply(out, in, status::ok);
        out.value = f_tell(&description->file);
        break;
    }
    case op::truncate: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if ((description->flags & write_only) == 0 || in.offset > fat32_max_file_bytes ||
            in.flags != 0 || in.length != 0 || in.name_length != 0) {
            reply(out, in, status::invalid); break;
        }
        const FRESULT seek_result = f_lseek(&description->file, static_cast<FSIZE_t>(in.offset));
        if (seek_result != FR_OK) { reply(out, in, from_fr(seek_result)); break; }
        const FRESULT truncate_result = f_truncate(&description->file);
        reply(out, in, from_fr(truncate_result));
        break;
    }
    case op::close: {
        open_record* item = find_open(session, in.handle);
        if (item == nullptr) { reply(out, in, status::bad_handle); break; }
        reply(out, in, release_open(*item));
        break;
    }
    case op::transfer: {
        open_record* source = find_open(session, in.handle);
        open_description* description = description_for(source);
        if (description == nullptr || in.offset == 0 || in.offset == session.pid) {
            reply(out, in, status::bad_handle); break;
        }
        client_session* target = nullptr;
        u32 target_index = 0;
        for (u32 i = 0; i < max_sessions; ++i) {
            if (sessions[i].pid == in.offset) { target = &sessions[i]; target_index = i; break; }
        }
        if (target == nullptr) { reply(out, in, status::would_block); break; }
        u32 slot = max_open;
        for (u32 i = 0; i < max_open; ++i) {
            if (!target->opens[i].used) { slot = i; break; }
        }
        u32 target_handle = 0;
        if (slot == max_open || !next_handle(target_index, target_handle) ||
            description->references == 0xffffffffu) {
            reply(out, in, status::full); break;
        }
        target->opens[slot] = open_record{true, target_handle, source->description};
        ++description->references;
        reply(out, in, status::ok);
        out.handle = target_handle;
        break;
    }
    case op::clone_session: {
        if (in.handle != 0 || in.flags != 0 || in.reserved != 0 ||
            in.length != 0 || in.name_length != 0) {
            reply(out, in, status::invalid); break;
        }
        reply(out, in, clone_session(session, in.offset));
        break;
    }
    case op::replace_begin: {
        char path[max_name]{};
        if (!request_path(in, path) || in.length > fat32_max_file_bytes) {
            reply(out, in, status::invalid); break;
        }
        if (staging_active) {
            reply(out, in, status::busy);
            break;
        }
        FILINFO info{};
        const FRESULT target_result = f_stat(path, &info);
        const bool target_exists = target_result == FR_OK;
        if (target_exists && (info.fattrib & AM_DIR) != 0) { reply(out, in, status::invalid); break; }
        if (target_result != FR_OK && target_result != FR_NO_FILE) {
            reply(out, in, from_fr(target_result)); break;
        }
        if (any_open(session, path)) { reply(out, in, status::busy); break; }
        const u64 required = required_staging_bytes(in.length);
        if (required > available_bytes()) { reply(out, in, status::no_space); break; }
        const FRESULT opened = f_open(&staging_file, temp_name, FA_CREATE_ALWAYS | FA_WRITE);
        if (opened != FR_OK) { reply(out, in, from_fr(opened)); break; }
        staging_open = true;
        staging_active = true;
        staging_owner = session.pid;
        staging_written = 0;
        staging_total = in.length;
        copy_text(staging_path, path);
        reply(out, in, status::ok);
        out.value = staging_total;
        break;
    }
    case op::replace_chunk: {
        if (!staging_active || staging_owner != session.pid) { reply(out, in, status::bad_handle); break; }
        if (!staging_open || in.offset != staging_written || in.length > sizeof(in.data) ||
            in.length > staging_total - staging_written) { reply(out, in, status::invalid); break; }
        UINT written = 0;
        const FRESULT result = f_write(&staging_file, in.data, in.length, &written);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        staging_written += written;
        reply(out, in, written == in.length ? status::ok : status::no_space);
        out.value = staging_written;
        break;
    }
    case op::replace_commit: {
        if (!staging_active || staging_owner != session.pid) { reply(out, in, status::bad_handle); break; }
        if (!staging_open || staging_written != staging_total) { reply(out, in, status::invalid); break; }
        for (const auto& owner_session : sessions) {
            if (any_open(owner_session, staging_path)) { reply(out, in, status::busy); return; }
        }
        FRESULT result = f_sync(&staging_file);
        const FRESULT closed = f_close(&staging_file);
        if (result == FR_OK) { result = closed; }
        staging_open = false;
        if (result != FR_OK) {
            abort_staging();
            reply(out, in, from_fr(result));
            break;
        }
        FILINFO info{};
        const FRESULT target_result = f_stat(staging_path, &info);
        const bool target_exists = target_result == FR_OK;
        if (!target_exists && target_result != FR_NO_FILE) {
            abort_staging();
            reply(out, in, from_fr(target_result));
            break;
        }
        if (target_exists && (info.fattrib & AM_DIR) != 0) {
            abort_staging();
            reply(out, in, status::invalid);
            break;
        }
        const file_identity_key old_target_key = target_exists ? identity_key(info) : file_identity_key{};
        u16 target_inode = 0;
        if (target_exists) {
            if (!identity_for_info(info, target_inode)) {
                abort_staging();
                reply(out, in, status::full);
                break;
            }
        } else if (!can_allocate_identity()) {
            abort_staging();
            reply(out, in, status::full);
            break;
        }
        if (!write_journal(staging_path)) {
            recovery_failed = true;
            staging_active = false;
            staging_owner = 0;
            reply(out, in, status::io);
            break;
        }
        bool failed = false;
        if (target_exists) {
            if (!remove_if_present(backup_name) || f_rename(staging_path, backup_name) != FR_OK) {
                failed = true;
            }
        }
        if (!failed && f_rename(temp_name, staging_path) != FR_OK) {
            failed = true;
            if (target_exists) {
                if (f_rename(backup_name, staging_path) != FR_OK) {
                    recovery_failed = true;
                } else {
                    FILINFO restored_info{};
                    if (f_stat(staging_path, &restored_info) != FR_OK ||
                        !move_identity(old_target_key, identity_key(restored_info), target_inode)) {
                        recovery_failed = true;
                    }
                }
            }
        }
        if (failed) {
            recovery_failed = true;
            staging_active = false;
            staging_owner = 0;
            reply(out, in, status::io);
            break;
        }
        if (disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
            recovery_failed = true;
            staging_active = false;
            staging_owner = 0;
            reply(out, in, status::io);
            break;
        }
        FILINFO committed_info{};
        if (f_stat(staging_path, &committed_info) != FR_OK ||
            (target_exists
                ? !move_identity(old_target_key, identity_key(committed_info), target_inode)
                : !identity_for_info(committed_info, target_inode))) {
            recovery_failed = true;
            staging_active = false;
            staging_owner = 0;
            reply(out, in, status::io);
            break;
        }
        if (!finish_recovery(staging_path)) { recovery_failed = true; }
        staging_active = false;
        staging_owner = 0;
        reply(out, in, recovery_failed ? status::io : status::ok);
        out.value = staging_written;
        staging_written = 0;
        staging_total = 0;
        staging_path[0] = '\0';
        break;
    }
    case op::replace_abort:
        if (!staging_active || staging_owner != session.pid) { reply(out, in, status::bad_handle); break; }
        abort_staging();
        reply(out, in, status::ok);
        break;
    case op::sync: {
        status code = status::ok;
        for (auto& item : descriptions) {
            if (!item.used || (item.flags & write_only) == 0) { continue; }
            const FRESULT synced = f_sync(&item.file);
            if (synced != FR_OK) { code = from_fr(synced); break; }
        }
        if (code == status::ok && staging_active && staging_open && f_sync(&staging_file) != FR_OK) {
            code = status::io;
        }
        if (code == status::ok && disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) { code = status::io; }
        reply(out, in, code);
        break;
    }
    case op::remove: {
        char path[max_name]{};
        if (!request_path(in, path)) { reply(out, in, status::invalid); break; }
        if (staging_active && same_path_object(staging_path, path)) { reply(out, in, status::busy); break; }
        for (const auto& owner_session : sessions) {
            if (any_open(owner_session, path)) { reply(out, in, status::busy); return; }
        }
        FILINFO info{};
        const FRESULT stat_result = f_stat(path, &info);
        if (stat_result != FR_OK) { reply(out, in, from_fr(stat_result)); break; }
        const FRESULT result = f_unlink(path);
        if (result == FR_OK) { (void)forget_identity(identity_key(info)); }
        reply(out, in, from_fr(result));
        break;
    }
    case op::mkdir: {
        char path[max_name]{};
        if (!request_path(in, path)) { reply(out, in, status::invalid); break; }
        reply(out, in, from_fr(f_mkdir(path)));
        break;
    }
    case op::rename: {
        char old_path[max_name]{};
        char new_path[max_name]{};
        if (!request_path(in, old_path) || in.length == 0 || in.length >= max_name ||
            !normalize_path(reinterpret_cast<const char*>(in.data), in.length, new_path, false)) {
            reply(out, in, status::invalid); break;
        }
        if (staging_active && (same_path_object(staging_path, old_path) || same_path_object(staging_path, new_path))) {
            reply(out, in, status::busy); break;
        }
        for (const auto& owner_session : sessions) {
            if (any_open(owner_session, old_path) || any_open(owner_session, new_path)) {
                reply(out, in, status::busy); return;
            }
        }
        FILINFO old_info{};
        const FRESULT old_stat = f_stat(old_path, &old_info);
        if (old_stat != FR_OK) { reply(out, in, from_fr(old_stat)); break; }
        u16 inode = 0;
        if (!identity_for_info(old_info, inode)) { reply(out, in, status::full); break; }
        const FRESULT renamed = f_rename(old_path, new_path);
        if (renamed != FR_OK) { reply(out, in, from_fr(renamed)); break; }
        FILINFO new_info{};
        if (f_stat(new_path, &new_info) != FR_OK ||
            !move_identity(identity_key(old_info), identity_key(new_info), inode)) {
            reply(out, in, status::io);
            break;
        }
        reply(out, in, status::ok);
        break;
    }
    default:
        reply(out, in, status::invalid);
        break;
    }
}
}

extern "C" int xos_user_main(const xos::startup_info*) {
    using namespace xos;
    const FRESULT mounted_result = f_mount(&fs, "", 1);
    mounted = mounted_result == FR_OK;
    if (mounted) { recover(); }
    const u64 own_pid = sdk::pid();
    for (;;) {
        retry_description_cleanup();
        for (u32 index = 0; index < max_sessions; ++index) {
            file_session_info info{};
            if (sdk::syscall(sys_file_session, index, reinterpret_cast<u64>(&info)) != 0) { continue; }
            if (info.pid == own_pid) { continue; }
            client_session& session = sessions[index];
            if (info.pid == 0) {
                if (session.pid != 0) { close_session(session); session = client_session{}; }
                continue;
            }
            if (session.pid != info.pid) {
                if (session.pid != 0) { close_session(session); }
                session = client_session{};
                session.pid = info.pid;
            }
            session.request_handle = info.request_handle;
            session.response_handle = info.response_handle;
            request& in = request_buffer;
            const i64 received = sdk::ipc_recv(session.request_handle, &in, sizeof(in));
            if (received <= 0) { continue; }
            response& out = response_buffer;
            out = response{};
            if (received != static_cast<i64>(sizeof(in))) {
                out.magic = file::response_magic;
                out.version = file::abi_version;
                out.status_code = static_cast<i32>(file::status::invalid);
            } else {
                handle(in, out, session, index);
            }
            (void)sdk::ipc_send(session.response_handle, &out, sizeof(out));
        }
        sdk::yield();
    }
}
