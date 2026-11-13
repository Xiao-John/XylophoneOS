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
constexpr char journal_temp_name[] = "XOSJRNT.TMP";
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

// A FIL is the shared inode's cache and FatFs lock. File offsets and access
// rights belong to descriptions; dup/fork references retain the description.
constexpr u32 max_file_objects = 256;
struct file_object {
    bool used;
    bool directory;
    bool anonymous;
    bool unlinked;
    bool null_device;
    bool closed;
    u32 references;
    u32 parent; // 0 is the permanent volume root.
    u16 inode;
    u32 directory_sector;
    u16 directory_offset;
    FIL file;
    char name[max_name];
    char backing[13]; // Reserved root name for an unlinked, referenced object.
    u32 metadata_attrib; // FAT attribute snapshot (AM_RDO drives mode projection).
    u64 mtime_sec;       // FAT mtime in Unix seconds; 0 means unknown.
};

struct open_description {
    bool used;
    u32 references;
    u32 object;
    u32 flags;
    u32 position;
};

struct client_session {
    u64 pid;
    u64 parent_pid;
    u32 request_handle;
    u32 response_handle;
    u32 cwd;
    bool cwd_initialized;
    open_record opens[max_open];
};

FATFS fs;
bool mounted;
bool recovery_failed;
u64 maintenance_writer;
client_session sessions[max_sessions];
u32 generations[max_sessions];
open_description descriptions[max_open_descriptions];
file_object file_objects[max_file_objects];
file_object root_object{true, true, false, false, false, true, 0, 0, 1, 0, 0, {}, {}, {}, 0, 0};
request request_buffer;
response response_buffer;
u8 block_bench_buffer[4096];
FIL staging_file;
bool staging_active;
bool staging_open;
char staging_path[max_name];
u32 staging_parent;
char staging_leaf[max_name];
u64 staging_owner;
u32 staging_written;
u32 staging_total;

struct file_identity_key {
    u32 sector;
    u16 offset;
    u16 inode;
};

constexpr u16 dev_directory_inode = 0xfffe;
constexpr u16 null_device_inode = 0xffff;

// Inode 1 is the volume root; the top two identities are virtual objects.
// FAT identities are issued monotonically and
// never reused during this service lifetime, so removed entries cannot alias a
// later file. Once the 16-bit namespace is exhausted, identity queries fail.
constexpr u32 max_file_identities = 65532;
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
    return file_identity_count < max_file_identities && next_file_inode < dev_directory_inode;
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

// Byte-exact spelling comparison. names_equal() folds case, so a caller that
// must reach FatFs for a case-only rename needs the raw bytes instead.
bool names_equal_exact(const char* left, const char* right) {
    u32 i = 0;
    while (left[i] != '\0' && left[i] == right[i]) { ++i; }
    return left[i] == right[i];
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

// True when `target` names an entry below the directory described by
// `source`. Comparison uses the on-disk directory entry identity, so FAT long
// name / short alias spelling differences cannot hide a descendant. Returns
// -1 on an I/O error so the caller can fail closed instead of continuing.
int directory_is_ancestor(const FILINFO& source, const char* target) {
    const file_identity_key source_key = identity_key(source);
    if (source_key.sector == 0) { return -1; }
    const u32 target_length = text_length(target, max_name);
    u32 cut = target_length;
    while (cut > 0) {
        while (cut > 0 && target[cut - 1] != '/') { --cut; }
        if (cut == 0) { break; }
        const u32 ancestor_length = cut - 1;
        if (ancestor_length == 0) { break; }
        char ancestor[max_name]{};
        for (u32 i = 0; i < ancestor_length; ++i) { ancestor[i] = target[i]; }
        FILINFO info{};
        const FRESULT result = f_stat(ancestor, &info);
        if (result == FR_OK) {
            if (same_identity_key(identity_key(info), source_key)) { return 1; }
        } else if (result != FR_NO_FILE && result != FR_NO_PATH) {
            return -1;
        }
        cut = ancestor_length;
    }
    return 0;
}

bool reserved_component(const char* begin, u32 length) {
    // Match the namespace already reserved by the offline disk-transfer API.
    // It includes anonymous backing names and denies normal path operations.
    if (length >= 7 && upper(begin[0]) == 'X' && upper(begin[1]) == 'O' &&
        upper(begin[2]) == 'S' && begin[length - 4] == '.' &&
        upper(begin[length - 3]) == 'T' && upper(begin[length - 2]) == 'M' &&
        upper(begin[length - 1]) == 'P') { return true; }
    const char* reserved[] = {temp_name, backup_name, journal_name, journal_temp_name};
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

u64 fat_to_unix(u16 fdate, u16 ftime) {
    if (fdate == 0) { return 0; }
    const u32 year = 1980u + ((fdate >> 9) & 0x7fu);
    const u32 month = (fdate >> 5) & 0x0fu;
    const u32 day = fdate & 0x1fu;
    const u32 hour = (ftime >> 11) & 0x1fu;
    const u32 minute = (ftime >> 5) & 0x3fu;
    const u32 second = (ftime & 0x1fu) * 2u;
    if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) { return 0; }
    // Civil-from-days, valid for the FAT range (1980-2107).
    u32 y = year;
    const u32 m = month;
    y -= m <= 2 ? 1 : 0;
    const u32 era = y / 400u;
    const u32 yoe = y - era * 400u;
    const u32 mp = (m + 9u) % 12u;
    const u32 doy = (153u * mp + 2u) / 5u + day - 1u;
    const u32 doe = yoe * 365u + yoe / 4u - yoe / 100u + doy;
    const u64 days = static_cast<u64>(era) * 146097ull + doe - 719468ull;
    return days * 86400ull + hour * 3600ull + minute * 60ull + second;
}

bool unix_to_fat(u64 seconds, u16& fdate, u16& ftime) {
    if (seconds == 0) { return false; }
    const u64 days = seconds / 86400ull;
    const u32 rem = static_cast<u32>(seconds % 86400ull);
    const u64 z = days + 719468ull;
    const u64 era = z / 146097ull;
    const u64 doe = z - era * 146097ull;
    const u64 yoe = (doe - doe / 1460ull + doe / 36524ull - doe / 146096ull) / 365ull;
    const u64 year = yoe + era * 400ull;
    const u64 doy = doe - (365ull * yoe + yoe / 4ull - yoe / 100ull);
    const u64 mp = (5ull * doy + 2ull) / 153ull;
    const u64 day = doy - (153ull * mp + 2ull) / 5ull + 1ull;
    const u64 month = mp < 10ull ? mp + 3ull : mp - 9ull;
    const u64 calendar_year = month <= 2ull ? year + 1ull : year;
    if (calendar_year < 1980ull || calendar_year > 2107ull) { return false; }
    fdate = static_cast<u16>(((calendar_year - 1980ull) << 9)
                             | (month << 5) | day);
    ftime = static_cast<u16>(((rem / 3600u) << 11) | (((rem / 60u) % 60u) << 5)
                             | ((rem % 60u) / 2u));
    return true;
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
    case FR_WRITE_PROTECTED: return status::read_only_volume;
    case FR_DENIED: return status::access_denied;
    case FR_INVALID_OBJECT: return status::invalid;
    case FR_NOT_ENOUGH_CORE:
    case FR_MKFS_ABORTED: return status::no_space;
    default: return status::io;
    }
}

FIL& file_for(const open_description& description);

status object_path(u32 object, char* path, bool logical);
status append_path(const char* parent, const char* leaf, char* path);

constexpr u32 mode_regular = 0100000u;
constexpr u32 mode_directory = 0040000u;
constexpr u32 metadata_record_bytes = 24;

void write_stat_metadata(response& out, bool directory, u32 attrib, u64 mtime) {
    const u32 permissions = directory ? 0755u : (((attrib & AM_RDO) != 0) ? 0444u : 0644u);
    const u32 mode = (directory ? mode_directory : mode_regular) | permissions;
    u8* record = out.data;
    record[0] = 'F'; record[1] = 'M'; record[2] = 'E'; record[3] = 'T';
    record[4] = 1; record[5] = 0;                 // u16 version = 1
    record[6] = static_cast<u8>(metadata_record_bytes);
    record[7] = 0;                                // u16 record length = 24
    for (u32 i = 0; i < 8; ++i) { record[8 + i] = static_cast<u8>(mtime >> (8 * i)); }
    for (u32 i = 0; i < 4; ++i) { record[16 + i] = 0; } // mtime_nsec = 0 (FAT)
    for (u32 i = 0; i < 4; ++i) { record[20 + i] = static_cast<u8>(mode >> (8 * i)); }
    out.length = metadata_record_bytes;
}

status file_object_path(const file_object& object, char* path) {
    char parent[max_name];
    const status code = object_path(object.parent, parent, false);
    if (code != status::ok) { return code; }
    return append_path(parent, object.name, path);
}

status seek_description(open_description& description, u32 position) {
    return from_fr(f_lseek(&file_for(description), static_cast<FSIZE_t>(position)));
}

// Write zeros at the current end of file. FatFs extends a file when f_lseek
// moves past EOF, but the newly allocated clusters are not cleared, so every
// extension must go through real zero bytes instead of a bare seek.
status zero_fill(open_description& description, u32 count) {
    static const u8 zeros[512] = {};
    while (count != 0) {
        const UINT chunk = count > sizeof(zeros) ? static_cast<UINT>(sizeof(zeros))
                                                 : static_cast<UINT>(count);
        UINT written = 0;
        const FRESULT result = f_write(&file_for(description), zeros, chunk, &written);
        if (result != FR_OK) { return from_fr(result); }
        if (written != chunk) { return status::no_space; }
        count -= written;
    }
    return status::ok;
}

status grow_with_zeros(open_description& description, u32 from, u32 to) {
    if (to <= from) { return status::ok; }
    const status seek = seek_description(description, from);
    if (seek != status::ok) { return seek; }
    return zero_fill(description, to - from);
}

file_object& object_for(const open_description& description) {
    return description.object == 0 ? root_object : file_objects[description.object - 1];
}

FIL& file_for(const open_description& description) {
    return object_for(description).file;
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

void retain_object(u32 object) {
    if (object != 0) { ++file_objects[object - 1].references; }
}

status release_object(u32 object);

status object_path(u32 object, char* path, bool logical = false) {
    u32 chain[max_name / 2];
    u32 count = 0;
    while (object != 0) {
        const file_object& item = file_objects[object - 1];
        if (count == max_name / 2) { return status::name_too_long; }
        chain[count++] = object;
        if (item.unlinked) {
            if (logical) { return status::not_found; }
            break;
        }
        object = item.parent;
    }
    u32 used = 0;
    while (count != 0) {
        const file_object& item = file_objects[chain[--count] - 1];
        const char* name = item.unlinked ? item.backing : item.name;
        const u32 length = text_length(name, max_name);
        if (used + (used != 0) + length >= max_name) { return status::name_too_long; }
        if (used != 0) { path[used++] = '/'; }
        for (u32 i = 0; i < length; ++i) { path[used++] = name[i]; }
    }
    path[used] = '\0';
    return status::ok;
}

file_identity_key key_for_object(const file_object& object) {
    return file_identity_key{object.directory_sector, object.directory_offset, object.inode};
}

u32 find_object(file_identity_key key) {
    for (u32 i = 0; i < max_file_objects; ++i) {
        if (file_objects[i].used && same_identity_key(key_for_object(file_objects[i]), key)) {
            return i + 1;
        }
    }
    return 0;
}

status cleanup_object(u32 index) {
    file_object& object = file_objects[index - 1];
    if (!object.used || object.references != 0) { return status::invalid; }
    if (!object.directory && !object.null_device && !object.closed) {
        const FRESULT result = f_close(&object.file);
        if (result != FR_OK) { return from_fr(result); }
        object.closed = true;
    }
    if (object.unlinked) {
        if (!anonymous_path(object.backing)) { return status::io; }
        const FRESULT result = f_unlink(object.backing);
        if (result != FR_OK && result != FR_NO_FILE && result != FR_NO_PATH) { return from_fr(result); }
        (void)forget_identity(key_for_object(object));
    }
    const u32 parent = object.parent;
    object = file_object{};
    return release_object(parent);
}

status release_object(u32 object) {
    if (object == 0) { return status::ok; }
    file_object& item = file_objects[object - 1];
    if (--item.references != 0) { return status::ok; }
    return cleanup_object(object);
}

status cleanup_description(open_description& description) {
    if (!description.used || description.references != 0) { return status::invalid; }
    const u32 object = description.object;
    description = open_description{};
    return release_object(object);
}

status release_open(open_record& item) {
    open_description* description = description_for(&item);
    status result = status::ok;
    if (description != nullptr && --description->references == 0) {
        result = cleanup_description(*description);
    }
    item = open_record{};
    return result;
}

void retry_description_cleanup() {
    for (u32 i = 0; i < max_file_objects; ++i) {
        if (file_objects[i].used && file_objects[i].references == 0) { (void)cleanup_object(i + 1); }
    }
}

struct path_reference {
    u32 parent = 0;
    status error = status::ok;
    char leaf[max_name]{};
    char path[max_name]{};
    ~path_reference() { (void)release_object(parent); }
};

status append_path(const char* parent, const char* leaf, char* path) {
    const u32 base = text_length(parent, max_name);
    const u32 length = text_length(leaf, max_name);
    if (base + (base != 0 && length != 0) + length >= max_name) { return status::name_too_long; }
    u32 used = 0;
    for (; used < base; ++used) { path[used] = parent[used]; }
    if (base != 0 && length != 0) { path[used++] = '/'; }
    for (u32 i = 0; i < length; ++i) { path[used++] = leaf[i]; }
    path[used] = '\0';
    return status::ok;
}

// f_stat may echo the requested LFN spelling. Enumerating the parent once
// when retaining a directory gives getcwd the stored name, including SFN use.
status directory_name(u32 parent, file_identity_key key, char* name) {
    char path[max_name]{};
    status code = object_path(parent, path);
    if (code != status::ok) { return code; }
    DIR directory{};
    FRESULT result = f_opendir(&directory, path);
    if (result != FR_OK) { return from_fr(result); }
    FILINFO info{};
    bool found = false;
    while ((result = f_readdir(&directory, &info)) == FR_OK && info.fname[0] != '\0') {
        if (same_identity_key(identity_key(info), key)) {
            copy_text(name, info.fname);
            found = true;
            break;
        }
    }
    const FRESULT closed = f_closedir(&directory);
    if (result != FR_OK) { return from_fr(result); }
    if (closed != FR_OK) { return from_fr(closed); }
    return found ? status::ok : status::not_found;
}

status acquire_directory(u32 parent, const char* path, u32& index) {
    FILINFO info{};
    const FRESULT result = f_stat(path, &info);
    if (result != FR_OK) { return from_fr(result); }
    if ((info.fattrib & AM_DIR) == 0) { return status::not_directory; }
    index = find_object(identity_key(info));
    if (index != 0) { retain_object(index); return status::ok; }
    for (u32 i = 0; i < max_file_objects; ++i) {
        if (file_objects[i].used) { continue; }
        u16 inode = 0;
        if (!identity_for_info(info, inode)) { return status::full; }
        file_object& object = file_objects[i];
        const status named = directory_name(parent, identity_key(info), object.name);
        if (named != status::ok) { return named; }
        object.used = true;
        object.directory = true;
        object.references = 1;
        object.parent = parent;
        object.inode = inode;
        object.directory_sector = info.xos_dir_sector;
        object.directory_offset = info.xos_dir_offset;
        object.metadata_attrib = info.fattrib;
        object.mtime_sec = fat_to_unix(info.fdate, info.ftime);
        retain_object(parent);
        index = i + 1;
        return status::ok;
    }
    return status::full;
}

bool equals_path(const char* path, const char* name);

status resolve_service_path(client_session& session, const char* source, u32 length,
                            path_reference& output, bool allow_root = false,
                            bool allow_trailing_slash = false) {
    if (length == 0) { return status::not_found; }
    if (length >= max_name) { return status::name_too_long; }
    if (!xos::text::valid(source, length)) { return status::invalid; }
    for (u32 i = 0; i < length; ++i) {
        const u8 c = static_cast<u8>(source[i]);
        if (c < 0x20 || c == 0x7f || c == '\\' || c == ':' || c == '*' || c == '?' ||
            c == '"' || c == '<' || c == '>' || c == '|') { return status::invalid; }
    }
    if (length > 1 && source[length - 1] == '/' && !allow_trailing_slash) { return status::invalid; }
    output.parent = source[0] == '/' ? 0 : session.cwd;
    retain_object(output.parent);
    u32 position = 0;
    while (position < length) {
        while (position < length && source[position] == '/') { ++position; }
        const u32 begin = position;
        while (position < length && source[position] != '/') { ++position; }
        const u32 size = position - begin;
        if (size == 0 || (size == 1 && source[begin] == '.')) { continue; }
        if (size == 2 && source[begin] == '.' && source[begin + 1] == '.') {
            const u32 parent = output.parent == 0 ? 0 : file_objects[output.parent - 1].parent;
            retain_object(parent);
            (void)release_object(output.parent);
            output.parent = parent;
            continue;
        }
        if (source[position - 1] == '.' || source[position - 1] == ' ' ||
            reserved_component(source + begin, size)) { return status::invalid; }
        if (output.parent != 0 && file_objects[output.parent - 1].unlinked) { return status::not_found; }
        char parent_path[max_name]{};
        status code = object_path(output.parent, parent_path);
        if (code != status::ok) { return code; }
        for (u32 i = 0; i < size; ++i) { output.leaf[i] = source[begin + i]; }
        output.leaf[size] = '\0';
        code = append_path(parent_path, output.leaf, output.path);
        if (code != status::ok) { return code; }
        u32 next = position;
        while (next < length && source[next] == '/') { ++next; }
        // Recognize dev only after walking preceding components, so missing
        // intermediate directories still fail even when followed by "..".
        if (output.parent == 0 && size == 3 && source[begin] == 'd' &&
            source[begin + 1] == 'e' && source[begin + 2] == 'v') {
            bool null_device = false;
            while (next < length) {
                const u32 part = next;
                while (next < length && source[next] != '/') { ++next; }
                const u32 count = next - part;
                if (count == 1 && source[part] == '.') {
                    // A dot still requires the preceding object to be a directory.
                    if (null_device) { return status::not_directory; }
                } else if (!null_device && count == 4 && source[part] == 'n' &&
                           source[part + 1] == 'u' && source[part + 2] == 'l' &&
                           source[part + 3] == 'l') {
                    null_device = true;
                } else {
                    return null_device ? status::not_directory : status::not_found;
                }
                while (next < length && source[next] == '/') { ++next; }
            }
            if (null_device && source[length - 1] == '/') { return status::not_directory; }
            copy_text(output.path, null_device ? "dev/null" : "dev");
            copy_text(output.leaf, null_device ? "null" : "dev");
            return status::ok;
        }
        if (next == length && source[length - 1] != '/') { return status::ok; }
        u32 directory = 0;
        code = acquire_directory(output.parent, output.path, directory);
        if (code != status::ok) { return code; }
        (void)release_object(output.parent);
        output.parent = directory;
        output.leaf[0] = '\0';
    }
    if (output.parent == 0 && !allow_root) { return status::invalid; }
    return object_path(output.parent, output.path);
}

bool request_path(const request& in, client_session& session, path_reference& output,
                  bool allow_root = false, bool allow_trailing_slash = false) {
    output.error = resolve_service_path(session, in.name, in.name_length, output,
                                        allow_root, allow_trailing_slash);
    return output.error == status::ok;
}

status directory_from_path(path_reference& path, u32& object) {
    if (path.leaf[0] == '\0') {
        object = path.parent;
        retain_object(object);
        return status::ok;
    }
    return acquire_directory(path.parent, path.path, object);
}

bool equals_path(const char* path, const char* name) {
    if (path == nullptr) { return false; }
    if (path[0] == '/') { ++path; }
    for (u32 index = 0; ; ++index) {
        if (path[index] != name[index]) { return false; }
        if (name[index] == '\0') { return true; }
    }
}

bool is_dev_directory(const char* path) { return equals_path(path, "dev"); }
bool is_null_device(const char* path) { return equals_path(path, "dev/null"); }

status open_null_object(u32& index) {
    for (u32 i = 0; i < max_file_objects; ++i) {
        if (file_objects[i].used && file_objects[i].null_device) {
            index = i + 1;
            retain_object(index);
            return status::ok;
        }
    }
    u32 slot = 0;
    while (slot < max_file_objects && file_objects[slot].used) { ++slot; }
    if (slot == max_file_objects) { return status::full; }
    file_object& object = file_objects[slot];
    object = file_object{};
    object.used = true;
    object.null_device = true;
    object.inode = null_device_inode;
    object.references = 1;
    index = slot + 1;
    return status::ok;
}

status open_file_object(path_reference& path, u32 flags, u32& index) {
    const u32 access = flags & open_access_mask;
    const u32 options = flags & open_option_mask;
    FILINFO info{};
    const FRESULT found = f_stat(path.path, &info);
    if (found != FR_OK && found != FR_NO_FILE) { return from_fr(found); }
    if (found == FR_OK && (info.fattrib & AM_DIR) != 0) { return status::is_directory; }
    if (found == FR_OK && (options & open_exclusive) != 0) { return status::exists; }
    if (found == FR_NO_FILE && (options & open_create) == 0) { return status::not_found; }
    index = found == FR_OK ? find_object(identity_key(info)) : 0;
    if (index != 0) {
        for (const auto& description : descriptions) {
            if (!description.used || description.object != index) { continue; }
            if (((flags & open_pin) != 0 && (description.flags & write_only) != 0) ||
                ((access & write_only) != 0 && (description.flags & open_pin) != 0)) {
                return status::busy;
            }
        }
        file_object& object = file_objects[index - 1];
        if ((access & write_only) != 0 &&
            ((object.file.flag & FA_WRITE) == 0 || (info.fattrib & AM_RDO) != 0)) {
            return status::access_denied;
        }
        retain_object(index);
    } else {
        u32 slot = 0;
        while (slot < max_file_objects && file_objects[slot].used) { ++slot; }
        u16 known_inode = 0;
        if (slot == max_file_objects ||
            (found == FR_OK ? !identity_for_info(info, known_inode) : !can_allocate_identity())) {
            return status::full;
        }
        file_object& object = file_objects[slot];
        object = file_object{};
        BYTE mode = FA_READ | FA_WRITE;
        if (found == FR_OK && (info.fattrib & AM_RDO) != 0) {
            if ((access & write_only) != 0) { return status::access_denied; }
            mode = FA_READ;
        }
        if ((options & open_exclusive) != 0) { mode |= FA_CREATE_NEW; }
        else if ((options & open_create) != 0) { mode |= FA_OPEN_ALWAYS; }
        FRESULT opened = f_open(&object.file, path.path, mode);
        if ((opened == FR_WRITE_PROTECTED || opened == FR_DENIED) && access == read_only && options == 0) {
            opened = f_open(&object.file, path.path, FA_READ);
        }
        if (opened != FR_OK) { return from_fr(opened); }
        object.used = true;
        object.references = 1;
        object.parent = path.parent;
        FILINFO opened_info{};
        if (f_stat(path.path, &opened_info) == FR_OK) {
            object.metadata_attrib = opened_info.fattrib;
            object.mtime_sec = fat_to_unix(opened_info.fdate, opened_info.ftime);
        }
        copy_text(object.name, path.leaf);
        retain_object(object.parent);
        index = slot + 1;
        const file_identity_key key = identity_key(object.file);
        object.directory_sector = key.sector;
        object.directory_offset = key.offset;
        if (!identity_for_file(object.file, object.inode)) {
            (void)release_object(index);
            return status::full;
        }
    }
    if ((options & open_truncate) != 0) {
        FIL& file = file_objects[index - 1].file;
        FRESULT result = f_lseek(&file, 0);
        if (result == FR_OK) { result = f_truncate(&file); }
        if (result == FR_OK) { result = f_sync(&file); }
        if (result != FR_OK) {
            (void)release_object(index);
            return from_fr(result);
        }
    }
    return status::ok;
}

status anonymous_name(char* path) {
    for (u32 attempt = 0; attempt < anonymous_serial_limit; ++attempt) {
        copy_text(path, "XOS00000.TMP");
        u32 serial = next_anonymous_serial;
        next_anonymous_serial = (next_anonymous_serial + 1) % anonymous_serial_limit;
        for (u32 digit = 0; digit < 5; ++digit) {
            path[7 - digit] = static_cast<char>('0' + serial % 10);
            serial /= 10;
        }
        FILINFO info{};
        const FRESULT result = f_stat(path, &info);
        if (result == FR_NO_FILE) { return status::ok; }
        if (result != FR_OK) { return from_fr(result); }
    }
    return status::full;
}

status directory_empty(const char* path) {
    DIR directory{};
    FRESULT result = f_opendir(&directory, path);
    if (result != FR_OK) { return from_fr(result); }
    FILINFO info{};
    result = f_readdir(&directory, &info);
    const FRESULT closed = f_closedir(&directory);
    if (result != FR_OK) { return from_fr(result); }
    if (closed != FR_OK) { return from_fr(closed); }
    return info.fname[0] == '\0' ? status::ok : status::not_empty;
}

status move_disk_object(const char* from, const char* to, const FILINFO& before) {
    const file_identity_key old_key = identity_key(before);
    u16 inode = 0;
    if (!identity_for_info(before, inode)) { return status::full; }
    const u32 index = find_object(old_key);
    const FRESULT result = index != 0 && !file_objects[index - 1].directory &&
        !file_objects[index - 1].closed
        ? f_rename_open(&file_objects[index - 1].file, from, to) : f_rename(from, to);
    if (result != FR_OK) {
        if (result == FR_DISK_ERR || result == FR_INT_ERR) { recovery_failed = true; }
        return from_fr(result);
    }
    FILINFO after{};
    if (f_stat(to, &after) != FR_OK || !move_identity(old_key, identity_key(after), inode)) {
        recovery_failed = true;
        return status::io;
    }
    if (index != 0) {
        file_objects[index - 1].directory_sector = after.xos_dir_sector;
        file_objects[index - 1].directory_offset = after.xos_dir_offset;
    }
    return status::ok;
}

void relocate_object(u32 index, u32 parent, const char* leaf) {
    if (index == 0) { return; }
    file_object& object = file_objects[index - 1];
    retain_object(parent);
    const u32 previous = object.parent;
    object.parent = parent;
    copy_text(object.name, leaf);
    (void)release_object(previous);
}

status detach_object(u32 index, const char* path, const FILINFO& info, const char* reserved = nullptr) {
    file_object& object = file_objects[index - 1];
    char hidden[13]{};
    status code = status::ok;
    if (reserved) copy_text(hidden, reserved);
    else code = anonymous_name(hidden);
    if (code != status::ok) { return code; }
    code = move_disk_object(path, hidden, info);
    if (code != status::ok) { return code; }
    object.unlinked = true;
    copy_text(object.backing, hidden);
    return status::ok;
}

bool refresh_staging_path() {
    if (!staging_active) { return true; }
    char parent[max_name]{};
    return object_path(staging_parent, parent, true) == status::ok &&
           append_path(parent, staging_leaf, staging_path) == status::ok;
}

bool cleanup_pending() {
    for (const auto& object : file_objects) {
        if (object.used && object.references == 0) { return true; }
    }
    return false;
}

void close_session(client_session& session) {
    (void)release_object(session.cwd);
    session.cwd = 0;
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
        (void)release_object(staging_parent);
        staging_parent = 0;
    }
}

bool remove_if_present(const char* path) {
    FILINFO info{};
    const FRESULT result = f_stat(path, &info);
    if (result == FR_NO_FILE || result == FR_NO_PATH) { return true; }
    return result == FR_OK && f_unlink(path) == FR_OK;
}

bool write_journal(const char* path) {
    // Publish a complete journal by rename; a short write must not leave a
    // truncated marker that makes the next boot fail closed forever.
    (void)remove_if_present(journal_temp_name);
    FIL file{};
    if (f_open(&file, journal_temp_name, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK) { return false; }
    const UINT length = static_cast<UINT>(text_length(path, max_name) + 1);
    UINT written = 0;
    FRESULT result = f_write(&file, path, length, &written);
    if (result == FR_OK) { result = f_sync(&file); }
    const FRESULT closed = f_close(&file);
    if (result != FR_OK || closed != FR_OK || written != length) {
        (void)remove_if_present(journal_temp_name);
        return false;
    }
    if (f_rename(journal_temp_name, journal_name) != FR_OK) {
        (void)remove_if_present(journal_temp_name);
        return false;
    }
    if (disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
        (void)remove_if_present(journal_name);
        return false;
    }
    return true;
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
bool finish_recovery(const char* path, bool remove_staging = true) {
    if (disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK ||
        (remove_staging && !remove_if_present(temp_name)) || !remove_if_present(journal_temp_name) ||
        !remove_if_present(backup_name) ||
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
        if (!remove_if_present(temp_name) || !remove_if_present(journal_temp_name) ||
            disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
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
        (target_result == FR_OK && backup_result == FR_OK &&
         ((target_info.fattrib ^ backup_info.fattrib) & AM_DIR) != 0) ||
        (temp_result == FR_OK && (temp_info.fattrib & AM_DIR) != 0)) {
        recovery_failed = true; return;
    }
    if (backup_result == FR_OK && missing(target_result) && f_rename(backup_name, path) != FR_OK) {
        recovery_failed = true; return;
    }
    if (!finish_recovery(path)) { recovery_failed = true; }
}

void recover_orphans() {
    DIR directory{};
    if (f_opendir(&directory, "") != FR_OK) { recovery_failed = true; return; }
    FILINFO info{};
    FRESULT result = FR_OK;
    while ((result = f_readdir(&directory, &info)) == FR_OK && info.fname[0] != '\0') {
        if (anonymous_path(info.fname) && f_unlink(info.fname) != FR_OK) {
            recovery_failed = true;
            break;
        }
    }
    const FRESULT closed = f_closedir(&directory);
    if (result != FR_OK || closed != FR_OK || disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
        recovery_failed = true;
    }
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

open_record* find_open(client_session& session, u32 handle);

void list_directory(const request& in, response& out, client_session& session) {
    path_reference resolved;
    if (in.handle != 0) {
        open_description* description = description_for(find_open(session, in.handle));
        if (description == nullptr) { reply(out, in, status::bad_handle); return; }
        if (!object_for(*description).directory) { reply(out, in, status::not_directory); return; }
        if (in.name_length != 0) { reply(out, in, status::invalid); return; }
        resolved.error = object_path(description->object, resolved.path);
        if (resolved.error != status::ok) { reply(out, in, resolved.error); return; }
    } else if (!request_path(in, session, resolved, true, true)) {
        reply(out, in, resolved.error); return;
    }
    const char* path = resolved.path;
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
    retain_object(source.cwd);
    (void)release_object(target->cwd);
    target->cwd = source.cwd;
    target->cwd_initialized = source.cwd_initialized;
    target->pid = child_pid;
    target->parent_pid = child_info.parent_pid;
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
        (void)release_object(target->cwd);
        target->cwd = 0;
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
    (void)release_object(staging_parent);
    staging_parent = 0;
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

status replace_namespace(const char* source, const char* target, const FILINFO& source_info,
                         const FILINFO* target_info, bool journal_new = false) {
    if (target_info == nullptr) {
        if (!journal_new) { return move_disk_object(source, target, source_info); }
        if (!write_journal(target)) { recovery_failed = true; return status::io; }
        const status code = move_disk_object(source, target, source_info);
        if (code != status::ok) { recovery_failed = true; return code; }
        if (!finish_recovery(target, false)) { recovery_failed = true; return status::io; }
        return status::ok;
    }
    const u32 replaced = find_object(identity_key(*target_info));
    char reserved_hidden[13]{};
    if (replaced != 0) {
        const status reserved = anonymous_name(reserved_hidden);
        if (reserved != status::ok) return reserved;
    }
    FILINFO backup_info{};
    if (!missing(f_stat(backup_name, &backup_info))) { return status::busy; }
    if (!write_journal(target)) {
        if (journal_new) { recovery_failed = true; }
        return status::io;
    }
    status code = move_disk_object(target, backup_name, *target_info);
    if (code != status::ok) { recovery_failed = true; return code; }
    if (f_stat(backup_name, &backup_info) != FR_OK) { recovery_failed = true; return status::io; }
    code = move_disk_object(source, target, source_info);
    if (code != status::ok) {
        if (move_disk_object(backup_name, target, backup_info) == status::ok) {
            if (f_unlink(journal_name) != FR_OK) { recovery_failed = true; }
        } else { recovery_failed = true; }
        return code;
    }
    if (replaced != 0) {
        code = detach_object(replaced, backup_name, backup_info, reserved_hidden);
        if (code != status::ok) { recovery_failed = true; return code; }
    } else {
        const FRESULT removed = f_unlink(backup_name);
        if (removed != FR_OK) { recovery_failed = true; return from_fr(removed); }
        (void)forget_identity(identity_key(backup_info));
    }
    // An unrelated replace transaction can still own XOSTMP.TMP. A rename
    // commits only its journal and backup; never abort that other transaction.
    if (!finish_recovery(target, false)) { recovery_failed = true; return status::io; }
    return status::ok;
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
        if (cleanup_pending()) { reply(out, in, status::busy); return; }
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
        if (cleanup_pending()) { reply(out, in, status::busy); return; }
        if (sdk::syscall(sys_block_sync) != 0) { reply(out, in, status::io); return; }
        maintenance_writer = 0;
        reply(out, in, status::ok); return;
    }
    const bool mutating = operation == op::anonymous || operation == op::anonymous_seal ||
        operation == op::clone_session || operation == op::write || operation == op::replace_begin ||
        operation == op::replace_chunk || operation == op::replace_commit || operation == op::replace_abort ||
        operation == op::remove || operation == op::mkdir || operation == op::rename || operation == op::sync ||
        operation == op::truncate || operation == op::set_metadata ||
        (operation == op::open && ((in.flags & open_access_mask) != read_only ||
                                  (in.flags & open_option_mask) != 0));
    if (mutating && (gate.owner_pid != 0 || maintenance_writer != 0) &&
        (gate.owner_pid == 0 || gate.worker_pid != session.pid || maintenance_writer != session.pid)) {
        reply(out, in, status::busy); return;
    }
    switch (operation) {
    case op::list:
        list_directory(in, out, session);
        break;
    case op::stat: {
        path_reference resolved;
        if (!request_path(in, session, resolved, true, true)) { reply(out, in, resolved.error); break; }
        const char* path = resolved.path;
        if (path[0] == '\0') {
            reply(out, in, status::ok);
            out.flags = stat_is_directory;
            out.reserved = 1;
            break;
        }
        if (is_dev_directory(path)) {
            reply(out, in, status::ok);
            out.value = 0;
            out.reserved = dev_directory_inode;
            out.flags = stat_is_directory;
            break;
        }
        if (is_null_device(path)) {
            reply(out, in, status::ok);
            out.value = 0;
            out.reserved = null_device_inode;
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
        write_stat_metadata(out, (info.fattrib & AM_DIR) != 0, info.fattrib,
                            fat_to_unix(info.fdate, info.ftime));
        const u32 object = find_object(identity_key(info));
        if (object != 0) {
            const file_object& retained = file_objects[object - 1];
            if (!retained.directory && !retained.closed) { out.value = f_size(&retained.file); }
            if (retained.unlinked) { out.flags |= stat_unlinked; }
        }
        break;
    }
    case op::cwd_set: {
        if ((in.flags & ~1u) != 0 || in.length != 0 || in.reserved != 0) {
            reply(out, in, status::invalid); break;
        }
        client_session* target = &session;
        if (in.offset != 0 && in.offset != session.pid) {
            target = nullptr;
            for (auto& candidate : sessions) {
                if (candidate.pid == in.offset) { target = &candidate; break; }
            }
            if (target == nullptr) { reply(out, in, status::would_block); break; }
            if (target->parent_pid != session.pid) { reply(out, in, status::invalid); break; }
            if (target->cwd_initialized) { reply(out, in, status::busy); break; }
        }
        if ((in.flags & 1u) != 0 && target->cwd_initialized) { reply(out, in, status::ok); break; }
        u32 directory = 0;
        if (in.handle != 0) {
            open_description* description = description_for(find_open(session, in.handle));
            if (description == nullptr) { reply(out, in, status::bad_handle); break; }
            if (!object_for(*description).directory) { reply(out, in, status::not_directory); break; }
            if (in.name_length != 0) { reply(out, in, status::invalid); break; }
            directory = description->object;
            retain_object(directory);
        } else if (in.name_length == 0) {
            directory = session.cwd;
            retain_object(directory);
        } else {
            path_reference resolved;
            if (!request_path(in, session, resolved, true, true)) { reply(out, in, resolved.error); break; }
            const status code = directory_from_path(resolved, directory);
            if (code != status::ok) { reply(out, in, code); break; }
        }
        const u32 previous = target->cwd;
        target->cwd = directory;
        target->cwd_initialized = true;
        (void)release_object(previous);
        reply(out, in, status::ok);
        break;
    }
    case op::cwd_get:
    case op::resolve_path: {
        path_reference resolved;
        status code = status::ok;
        if (operation == op::cwd_get) {
            code = object_path(session.cwd, resolved.path, true);
        } else {
            if (!request_path(in, session, resolved, true, true)) { reply(out, in, resolved.error); break; }
            char parent[max_name]{};
            code = object_path(resolved.parent, parent, true);
        }
        if (code != status::ok) { reply(out, in, code); break; }
        const u32 length = text_length(resolved.path, max_name);
        if (length + 1 >= max_name) { reply(out, in, status::name_too_long); break; }
        reply(out, in, status::ok);
        out.name[0] = '/';
        for (u32 i = 0; i <= length; ++i) { out.name[i + 1] = resolved.path[i]; }
        out.name_length = length + 1;
        break;
    }
    case op::anonymous:
    case op::open: {
        const bool anonymous = operation == op::anonymous;
        const u32 flags = anonymous ? read_write | open_create | open_exclusive : in.flags;
        const u32 access = flags & open_access_mask;
        const u32 options = flags & open_option_mask;
        const bool directory = (flags & open_directory) != 0;
        path_reference resolved;
        if (anonymous) {
            bool empty = in.handle == 0 && in.flags == 0 && in.reserved == 0 && in.offset == 0 &&
                in.length == 0 && in.name_length == 0;
            for (char byte : in.name) { empty = empty && byte == 0; }
            for (u8 byte : in.data) { empty = empty && byte == 0; }
            if (!empty) { reply(out, in, status::invalid); break; }
            const status named = anonymous_name(resolved.path);
            if (named != status::ok) { reply(out, in, named); break; }
            copy_text(resolved.leaf, resolved.path);
        } else if (!request_path(in, session, resolved, directory, directory)) {
            reply(out, in, resolved.error); break;
        }
        if ((flags & ~open_valid_mask) != 0 ||
            (access != read_only && access != write_only && access != read_write) ||
            ((options & open_exclusive) != 0 && (options & open_create) == 0) ||
            ((options & (open_truncate | open_append)) != 0 && (access & write_only) == 0) ||
            (directory && (access != read_only || options != 0 || (flags & open_pin) != 0)) ||
            ((flags & open_pin) != 0 && (access != read_only || options != 0))) {
            reply(out, in, status::invalid); break;
        }
        u32 slot = max_open, description_slot = max_open_descriptions;
        for (u32 i = 0; i < max_open; ++i) { if (!session.opens[i].used) { slot = i; break; } }
        for (u32 i = 0; i < max_open_descriptions; ++i) {
            if (!descriptions[i].used) { description_slot = i; break; }
        }
        u32 handle = 0;
        if (slot == max_open || description_slot == max_open_descriptions ||
            !next_handle(session_index, handle)) { reply(out, in, status::full); break; }
        u32 object = 0;
        if (!directory && is_null_device(resolved.path)) {
            // /dev/null always exists; O_CREAT|O_EXCL must report that.
            if ((options & open_exclusive) != 0) { reply(out, in, status::exists); break; }
            const status opened_null = open_null_object(object);
            if (opened_null != status::ok) { reply(out, in, opened_null); break; }
            open_description& null_description = descriptions[description_slot];
            null_description = open_description{true, 1, object, flags, 0};
            session.opens[slot] = open_record{true, handle, description_slot + 1};
            reply(out, in, status::ok);
            out.handle = handle;
            out.reserved = object_for(null_description).inode;
            out.value = 0;
            break;
        }
        const status opened = directory ? directory_from_path(resolved, object)
            : open_file_object(resolved, flags, object);
        if (opened != status::ok) { reply(out, in, opened); break; }
        open_description& description = descriptions[description_slot];
        description = open_description{true, 1, object, flags, 0};
        file_object& target = object_for(description);
        if (anonymous) {
            target.anonymous = true;
            target.unlinked = true;
            copy_text(target.backing, resolved.path);
        }
        if (!directory && (options & open_append) != 0 && (options & open_truncate) == 0) {
            description.position = static_cast<u32>(f_size(&target.file));
        }
        session.opens[slot] = open_record{true, handle, description_slot + 1};
        reply(out, in, status::ok);
        out.handle = handle;
        out.value = directory ? 0 : f_size(&target.file);
        out.flags = directory ? stat_is_directory : 0;
        out.reserved = target.inode;
        break;
    }
    case op::anonymous_seal: {
        bool empty = in.flags == 0 && in.reserved == 0 && in.offset == 0 &&
            in.length == 0 && in.name_length == 0;
        for (char byte : in.name) { empty = empty && byte == 0; }
        for (u8 byte : in.data) { empty = empty && byte == 0; }
        if (!empty) { reply(out, in, status::invalid); break; }
        open_description* description = description_for(find_open(session, in.handle));
        if (description == nullptr || !object_for(*description).anonymous ||
            description->references == 0) { reply(out, in, status::bad_handle); break; }
        description->flags = read_only;
        reply(out, in, status::ok);
        break;
    }
    case op::fstat: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        const file_object& object = object_for(*description);
        if (object.null_device) {
            reply(out, in, status::ok);
            out.value = 0;
            out.flags = 0;
            out.reserved = null_device_inode;
            break;
        }
        reply(out, in, status::ok);
        out.value = object.directory ? 0 : f_size(&object.file);
        out.flags = (object.directory ? stat_is_directory : 0) | (object.unlinked ? stat_unlinked : 0);
        out.reserved = object.inode;
        write_stat_metadata(out, object.directory, object.metadata_attrib, object.mtime_sec);
        break;
    }
    case op::read: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if (object_for(*description).directory) { reply(out, in, status::is_directory); break; }
        if ((description->flags & read_only) == 0) { reply(out, in, status::invalid); break; }
        if (object_for(*description).null_device) {
            reply(out, in, status::ok); out.length = 0; out.value = 0; break;
        }
        const u32 size = static_cast<u32>(f_size(&file_for(*description)));
        if (description->position >= size) {
            reply(out, in, status::ok);
            out.length = 0;
            out.value = 0;
            break;
        }
        UINT wanted = in.length > sizeof(out.data)
                          ? static_cast<UINT>(sizeof(out.data))
                          : static_cast<UINT>(in.length);
        const u32 remaining = size - description->position;
        if (wanted > remaining) { wanted = remaining; }
        const status seek = seek_description(*description, description->position);
        if (seek != status::ok) { reply(out, in, seek); break; }
        // reply() clears the buffer, so acknowledge before f_read fills data.
        reply(out, in, status::ok);
        UINT read = 0;
        const FRESULT result = f_read(&file_for(*description), out.data, wanted, &read);
        if (result != FR_OK && read == 0) { reply(out, in, from_fr(result)); break; }
        description->position += read;
        out.length = read;
        out.value = read;
        break;
    }
    case op::write: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if (object_for(*description).directory) { reply(out, in, status::is_directory); break; }
        if ((description->flags & write_only) == 0) { reply(out, in, status::invalid); break; }
        // POSIX: a zero-byte write is a pure no-op. It must not move the
        // offset, must not extend the file, and append mode gains nothing.
        if (in.length == 0) { reply(out, in, status::ok); out.value = 0; break; }
        if (object_for(*description).null_device) {
            if (description->position > fat32_max_file_bytes ||
                in.length > fat32_max_file_bytes - description->position) {
                reply(out, in, status::no_space); break;
            }
            reply(out, in, status::ok);
            out.value = in.length;
            description->position += in.length;
            break;
        }
        const u32 offset_before = description->position;
        u32 position = description->position;
        if ((description->flags & open_append) != 0) {
            position = static_cast<u32>(f_size(&file_for(*description)));
        }
        if (position > fat32_max_file_bytes || in.length > sizeof(in.data) ||
            in.length > fat32_max_file_bytes - position) { reply(out, in, status::no_space); break; }
        // A write past EOF leaves a hole that must read back as zeros; FatFs
        // would otherwise expose whatever the reused clusters contained.
        const u32 size = static_cast<u32>(f_size(&file_for(*description)));
        // Undo a failed write: drop any zero-fill extension first, then put
        // the offset back. The offset never lands past the restored length,
        // because f_lseek beyond EOF re-extends the file with uncleared
        // clusters. A failed restore of the length itself is a real fault;
        // the final reposition is best effort.
        auto undo_failed_write = [&]() {
            if (static_cast<u32>(f_size(&file_for(*description))) > size) {
                if (seek_description(*description, size) != status::ok ||
                    f_truncate(&file_for(*description)) != FR_OK) { recovery_failed = true; }
            }
            const u32 restore = offset_before <= size ? offset_before : size;
            (void)seek_description(*description, restore);
            description->position = offset_before;
        };
        const status grown = grow_with_zeros(*description, size, position);
        if (grown != status::ok) {
            // The caller sees the write fail; undo any zero-fill that already
            // extended the file so the failed write is not observable.
            undo_failed_write();
            reply(out, in, grown); break;
        }
        const status seek = seek_description(*description, position);
        if (seek != status::ok) {
            // The hole may already be on disk; a failed positioning must leave
            // the file exactly as it was before the write attempt.
            undo_failed_write();
            reply(out, in, seek); break;
        }
        UINT written = 0;
        const FRESULT result = f_write(&file_for(*description), in.data, in.length, &written);
        description->position = position + written;
        if (written == 0) {
            // in.length > 0 here, so zero bytes means the media is full
            // (FR_OK reports the short write) or the write errored outright.
            const status code = result == FR_OK ? status::no_space : from_fr(result);
            undo_failed_write();
            reply(out, in, code);
            break;
        }
        reply(out, in, status::ok);
        out.value = written;
        break;
    }
    case op::seek: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if (object_for(*description).directory) { reply(out, in, status::is_directory); break; }
        const i64 displacement = static_cast<i64>(in.offset);
        i64 base = 0;
        if (in.flags == seek_current) { base = static_cast<i64>(description->position); }
        else if (in.flags == seek_end) {
            base = object_for(*description).null_device
                ? 0 : static_cast<i64>(f_size(&file_for(*description)));
        }
        else if (in.flags != seek_set) { reply(out, in, status::invalid); break; }
        if ((displacement < 0 && displacement < -base) ||
            (displacement > 0 && base > static_cast<i64>(fat32_max_file_bytes) - displacement)) {
            reply(out, in, status::invalid); break;
        }
        const i64 target = base + displacement;
        if (target < 0 || target > fat32_max_file_bytes) { reply(out, in, status::invalid); break; }
        // Positioning is logical only: it must not change the file length.
        description->position = static_cast<u32>(target);
        reply(out, in, status::ok);
        out.value = description->position;
        break;
    }
    case op::truncate: {
        open_record* item = find_open(session, in.handle);
        open_description* description = description_for(item);
        if (description == nullptr) { reply(out, in, status::bad_handle); break; }
        if (object_for(*description).directory) { reply(out, in, status::is_directory); break; }
        if ((description->flags & write_only) == 0 || in.offset > fat32_max_file_bytes ||
            in.flags != 0 || in.length != 0 || in.name_length != 0) {
            reply(out, in, status::invalid); break;
        }
        if (object_for(*description).null_device) { reply(out, in, status::ok); break; }
        const u32 target = static_cast<u32>(in.offset);
        const u32 current = static_cast<u32>(f_size(&file_for(*description)));
        if (target > current) {
            const status grown = grow_with_zeros(*description, current, target);
            if (grown != status::ok) {
                // Do not report success for a partial extension: restore the
                // original length before returning the real failure.
                if (seek_description(*description, current) == status::ok) {
                    if (f_truncate(&file_for(*description)) != FR_OK) { recovery_failed = true; }
                } else { recovery_failed = true; }
                reply(out, in, grown); break;
            }
        } else if (target < current) {
            const status seek = seek_description(*description, target);
            if (seek != status::ok) { reply(out, in, seek); break; }
            const FRESULT truncate_result = f_truncate(&file_for(*description));
            if (truncate_result != FR_OK) { reply(out, in, from_fr(truncate_result)); break; }
        }
        const FRESULT synced = f_sync(&file_for(*description));
        if (synced != FR_OK) { reply(out, in, from_fr(synced)); break; }
        // ftruncate never changes the file offset.
        reply(out, in, status::ok);
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
        // A caller-supplied PID is not transfer authority: only the process
        // that created the target may inject handles. The kernel supplies the
        // authenticated parent, so an unrelated session cannot fill the quota.
        if (target->parent_pid == 0 || target->parent_pid != session.pid) {
            reply(out, in, status::invalid); break;
        }
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
        path_reference resolved;
        if (!request_path(in, session, resolved)) { reply(out, in, resolved.error); break; }
        const char* path = resolved.path;
        if (is_dev_directory(path) || is_null_device(path)) {
            reply(out, in, status::invalid); break;
        }
        if (in.length > fat32_max_file_bytes) { reply(out, in, status::invalid); break; }
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
        staging_parent = resolved.parent;
        retain_object(staging_parent);
        copy_text(staging_leaf, resolved.leaf);
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
        staging_written += written;
        reply(out, in, result != FR_OK ? from_fr(result) :
                       written == in.length ? status::ok : status::no_space);
        out.value = staging_written;
        break;
    }
    case op::replace_commit: {
        if (!staging_active || staging_owner != session.pid) { reply(out, in, status::bad_handle); break; }
        if (!staging_open || staging_written != staging_total) { reply(out, in, status::invalid); break; }
        if (!refresh_staging_path()) { abort_staging(); reply(out, in, status::not_found); break; }
        FRESULT result = f_sync(&staging_file);
        const FRESULT closed = f_close(&staging_file);
        if (result == FR_OK) { result = closed; }
        if (closed == FR_OK) { staging_open = false; }
        if (result != FR_OK) { abort_staging(); reply(out, in, from_fr(result)); break; }
        FILINFO target{}, source{};
        const FRESULT target_result = f_stat(staging_path, &target);
        if (target_result != FR_OK && target_result != FR_NO_FILE) {
            abort_staging(); reply(out, in, from_fr(target_result)); break;
        }
        if (target_result == FR_OK && (target.fattrib & AM_DIR) != 0) {
            abort_staging(); reply(out, in, status::is_directory); break;
        }
        if (f_stat(temp_name, &source) != FR_OK) { abort_staging(); reply(out, in, status::io); break; }
        const status committed = replace_namespace(temp_name, staging_path, source,
            target_result == FR_OK ? &target : nullptr, true);
        if (committed == status::ok && disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) { recovery_failed = true; }
        const u32 written = staging_written;
        if (!recovery_failed) { abort_staging(); }
        else {
            staging_active = false;
            staging_owner = 0;
            (void)release_object(staging_parent);
            staging_parent = 0;
        }
        reply(out, in, recovery_failed ? status::io : committed);
        out.value = written;
        break;
    }
    case op::replace_abort:
        if (!staging_active || staging_owner != session.pid) { reply(out, in, status::bad_handle); break; }
        abort_staging();
        reply(out, in, recovery_failed ? status::io : status::ok);
        break;
    case op::sync: {
        status code = status::ok;
        for (auto& item : file_objects) {
            if (!item.used || item.directory || item.closed) { continue; }
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
        path_reference resolved;
        if (!request_path(in, session, resolved)) { reply(out, in, resolved.error); break; }
        const char* path = resolved.path;
        if (resolved.leaf[0] == '\0') { reply(out, in, status::invalid); break; }
        if (staging_active && refresh_staging_path() && same_path_object(staging_path, path)) {
            reply(out, in, status::busy); break;
        }
        FILINFO info{};
        const FRESULT found = f_stat(path, &info);
        if (found != FR_OK) { reply(out, in, from_fr(found)); break; }
        if ((info.fattrib & AM_DIR) != 0) {
            if ((in.flags & allow_directory) == 0) { reply(out, in, status::invalid); break; }
            const status empty = directory_empty(path);
            if (empty != status::ok) { reply(out, in, empty); break; }
        }
        const u32 object = find_object(identity_key(info));
        if (object != 0) { reply(out, in, detach_object(object, path, info)); break; }
        const FRESULT removed = f_unlink(path);
        if (removed == FR_OK) { (void)forget_identity(identity_key(info)); }
        reply(out, in, from_fr(removed));
        break;
    }
    case op::mkdir: {
        path_reference resolved;
        if (!request_path(in, session, resolved)) { reply(out, in, resolved.error); break; }
        reply(out, in, from_fr(f_mkdir(resolved.path)));
        break;
    }
    case op::rename: {
        path_reference source, target;
        if (!request_path(in, session, source)) { reply(out, in, source.error); break; }
        target.error = resolve_service_path(session, reinterpret_cast<const char*>(in.data), in.length, target);
        if (target.error != status::ok) { reply(out, in, target.error); break; }
        if (source.leaf[0] == '\0' || target.leaf[0] == '\0') { reply(out, in, status::invalid); break; }
        const char* old_path = source.path;
        const char* new_path = target.path;
        if (staging_active && refresh_staging_path() &&
            (same_path_object(staging_path, old_path) || same_path_object(staging_path, new_path))) {
            reply(out, in, status::busy); break;
        }
        FILINFO old_info{}, new_info{};
        const FRESULT old_result = f_stat(old_path, &old_info);
        if (old_result != FR_OK) { reply(out, in, from_fr(old_result)); break; }
        const FRESULT new_result = f_stat(new_path, &new_info);
        if (new_result != FR_OK && !missing(new_result)) { reply(out, in, from_fr(new_result)); break; }
        const bool exists = new_result == FR_OK;
        const bool directory = (old_info.fattrib & AM_DIR) != 0;
        const u32 moving = find_object(identity_key(old_info));
        if (exists && same_identity_key(identity_key(old_info), identity_key(new_info))) {
            if (names_equal_exact(old_path, new_path)) { reply(out, in, status::ok); break; }
            const status code = move_disk_object(old_path, new_path, old_info);
            if (code == status::ok) { relocate_object(moving, target.parent, target.leaf); }
            reply(out, in, code); break;
        }
        if (directory) {
            const int ancestor = directory_is_ancestor(old_info, new_path);
            if (ancestor < 0) { reply(out, in, status::io); break; }
            if (ancestor > 0) { reply(out, in, status::invalid); break; }
        }
        if (exists) {
            const bool target_directory = (new_info.fattrib & AM_DIR) != 0;
            if (directory != target_directory) {
                reply(out, in, target_directory ? status::is_directory : status::not_directory); break;
            }
            if (directory) {
                const status empty = directory_empty(new_path);
                if (empty != status::ok) { reply(out, in, empty); break; }
            }
        }
        const status renamed = replace_namespace(old_path, new_path, old_info, exists ? &new_info : nullptr);
        if (renamed == status::ok) { relocate_object(moving, target.parent, target.leaf); }
        reply(out, in, renamed);
        break;
    }
    case op::set_metadata: {
        if (in.length != sizeof(metadata_request) || in.flags != 0 || in.offset != 0 ||
            in.reserved != 0 || (in.handle == 0 && in.name_length == 0) ||
            (in.handle != 0 && in.name_length != 0)) {
            reply(out, in, status::invalid);
            break;
        }
        metadata_request metadata{};
        for (u32 i = 0; i < sizeof(metadata); ++i) {
            reinterpret_cast<u8*>(&metadata)[i] = in.data[i];
        }
        if (metadata.version != 1 || metadata.reserved != 0 ||
            (metadata.mask & ~(metadata_read_only | metadata_mtime | metadata_atime)) != 0 ||
            (metadata.attr & ~static_cast<u16>(AM_RDO)) != 0) {
            reply(out, in, status::invalid);
            break;
        }
        if (((metadata.mask & metadata_atime) != 0 &&
             (metadata.atime_nsec < 0 || metadata.atime_nsec >= 1000000000)) ||
            ((metadata.mask & metadata_mtime) != 0 &&
             (metadata.mtime_nsec < 0 || metadata.mtime_nsec >= 1000000000))) {
            reply(out, in, status::invalid);
            break;
        }
        // Each metadata write is a single field; combined fields cannot be
        // committed atomically on this backend.
        u32 field_count = 0;
        for (u32 bit = 0; bit < 3; ++bit) {
            if ((metadata.mask & (1u << bit)) != 0) { ++field_count; }
        }
        if (field_count > 1) { reply(out, in, status::not_supported); break; }
        char path[max_name]{};
        file_object* object = nullptr;
        if (in.handle != 0) {
            open_description* description = description_for(find_open(session, in.handle));
            if (description == nullptr) { reply(out, in, status::bad_handle); break; }
            // Flush pending data so a later f_sync/f_close cannot rewrite the
            // directory entry with GET_FATTIME() and undo f_utime.
            const FRESULT synced = f_sync(&file_for(*description));
            if (synced != FR_OK) { reply(out, in, from_fr(synced)); break; }
            object = &object_for(*description);
            if (object->null_device || object->unlinked) { reply(out, in, status::not_supported); break; }
            const status named = file_object_path(*object, path);
            if (named != status::ok) { reply(out, in, named); break; }
        } else {
            path_reference resolved;
            if (!request_path(in, session, resolved)) { reply(out, in, resolved.error); break; }
            copy_text(path, resolved.path);
        }
        if ((metadata.mask & metadata_atime) != 0) { reply(out, in, status::not_supported); break; }
        FILINFO info{};
        const FRESULT found = f_stat(path, &info);
        if (found != FR_OK) { reply(out, in, from_fr(found)); break; }
        if ((metadata.mask & metadata_read_only) != 0) {
            // Directory RDO has no verified write enforcement on this backend.
            if ((info.fattrib & AM_DIR) != 0) { reply(out, in, status::not_supported); break; }
            const FRESULT changed = f_chmod(path, (metadata.attr & AM_RDO) != 0 ? AM_RDO : 0, AM_RDO);
            if (changed != FR_OK) { reply(out, in, from_fr(changed)); break; }
        }
        if ((metadata.mask & metadata_mtime) != 0) {
            u16 fdate = 0, ftime = 0;
            if (!unix_to_fat(static_cast<u64>(metadata.mtime_sec), fdate, ftime)) {
                reply(out, in, status::invalid);
                break;
            }
            FILINFO stamp{};
            stamp.fdate = fdate;
            stamp.ftime = ftime;
            const FRESULT touched = f_utime(path, &stamp);
            if (touched != FR_OK) { reply(out, in, from_fr(touched)); break; }
        }
        if (f_stat(path, &info) == FR_OK) {
            file_object* refreshed = object;
            if (refreshed == nullptr) {
                const u32 index = find_object(identity_key(info));
                if (index != 0) { refreshed = &file_objects[index - 1]; }
            }
            if (refreshed != nullptr) {
                refreshed->metadata_attrib = info.fattrib;
                refreshed->mtime_sec = fat_to_unix(info.fdate, info.ftime);
            }
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
    if (mounted) { recover(); if (!recovery_failed) { recover_orphans(); } }
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
            session.parent_pid = info.parent_pid;
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
