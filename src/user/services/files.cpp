#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>
#include "ff.h"
#include "diskio.h"

namespace {
using namespace xos;
using namespace xos::file;

constexpr const char* temp_name = "XOSTMP.TMP";
constexpr const char* backup_name = "XOSBAK.TMP";
constexpr const char* journal_name = "XOSJRNL.TMP";

struct open_record {
    bool used;
    FIL file;
    char name[max_name];
    u32 flags;
};

FATFS fs;
bool mounted;
bool recovery_failed;
open_record opens[max_open];
u8 staging[max_file_bytes];
bool staging_active;
char staging_name[max_name];
u32 staging_size;
u32 staging_total;
u32 staging_owner;

u32 text_length(const char* text, u32 limit) {
    u32 length = 0;
    while (length < limit && text[length] != '\0') { ++length; }
    return length;
}

char upper(char value) {
    return value >= 'a' && value <= 'z' ? static_cast<char>(value - 'a' + 'A') : value;
}

bool names_equal(const char* left, const char* right) {
    u32 i = 0;
    while (i < max_name && left[i] != '\0' && right[i] != '\0') {
        if (upper(left[i]) != upper(right[i])) { return false; }
        ++i;
    }
    return left[i] == '\0' && right[i] == '\0';
}

bool name_ok(const char* name) {
    const u32 length = text_length(name, max_name);
    if (length == 0 || length >= max_name) { return false; }
    for (u32 i = 0; i < length; ++i) {
        const char c = name[i];
        if (c < 33 || c > 126 || c == '/' || c == '\\' || c == ':' || c == '*' ||
            c == '?' || c == '"' || c == '<' || c == '>' || c == '|') { return false; }
    }
    if (names_equal(name, temp_name) || names_equal(name, backup_name) ||
        names_equal(name, journal_name)) { return false; }
    return true;
}

void copy_name(char* destination, const char* source) {
    u32 i = 0;
    for (; i + 1 < max_name && source[i] != '\0'; ++i) { destination[i] = source[i]; }
    destination[i] = '\0';
}

status from_fr(FRESULT result) {
    switch (result) {
    case FR_OK: return status::ok;
    case FR_NO_FILE:
    case FR_NO_PATH:
    case FR_INVALID_NAME: return status::not_found;
    case FR_TOO_MANY_OPEN_FILES: return status::full;
    case FR_EXIST: return status::busy;
    case FR_DENIED:
    case FR_WRITE_PROTECTED:
    case FR_INVALID_OBJECT: return status::invalid;
    case FR_NOT_ENOUGH_CORE:
    case FR_MKFS_ABORTED: return status::no_space;
    default: return status::io;
    }
}

bool file_exists(const char* name, FILINFO* info = nullptr) {
    FILINFO local{};
    FILINFO* target = info == nullptr ? &local : info;
    const FRESULT result = f_stat(name, target);
    return result == FR_OK && (target->fattrib & AM_DIR) == 0;
}

u32 count_files() {
    DIR dir{};
    if (f_opendir(&dir, "") != FR_OK) { return 0; }
    u32 count = 0;
    FILINFO info{};
    while (f_readdir(&dir, &info) == FR_OK && info.fname[0] != '\0') {
        if ((info.fattrib & AM_DIR) == 0) { ++count; }
    }
    (void)f_closedir(&dir);
    return count;
}

bool any_open(const char* name) {
    for (const auto& item : opens) {
        if (item.used && names_equal(item.name, name)) { return true; }
    }
    return false;
}

bool remove_if_present(const char* name) {
    if (!file_exists(name)) { return true; }
    return f_unlink(name) == FR_OK;
}

bool write_journal(const char* name) {
    FIL file{};
    if (f_open(&file, journal_name, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK) { return false; }
    UINT written = 0;
    const UINT length = static_cast<UINT>(text_length(name, max_name) + 1);
    const FRESULT result = f_write(&file, name, length, &written);
    const FRESULT synced = f_sync(&file);
    (void)f_close(&file);
    return result == FR_OK && synced == FR_OK && written == length;
}

bool read_journal(char* name) {
    FIL file{};
    if (f_open(&file, journal_name, FA_READ) != FR_OK) { return false; }
    UINT read = 0;
    for (u32 i = 0; i < max_name; ++i) { name[i] = 0; }
    const FRESULT result = f_read(&file, name, max_name - 1, &read);
    (void)f_close(&file);
    return result == FR_OK && read != 0;
}

void recover() {
    char name[max_name]{};
    if (!read_journal(name)) {
        (void)remove_if_present(temp_name);
        return;
    }
    if (!name_ok(name)) {
        recovery_failed = true;
        return;
    }
    const bool target = file_exists(name);
    const bool backup = file_exists(backup_name);
    if (backup) {
        if (!target) {
            if (f_rename(backup_name, name) != FR_OK) { recovery_failed = true; }
        } else {
            (void)remove_if_present(backup_name);
        }
    }
    (void)remove_if_present(temp_name);
    if (!recovery_failed) { (void)f_unlink(journal_name); }
    (void)disk_ioctl(0, CTRL_SYNC, nullptr);
}

void reply(response& out, const request& in, status code) {
    out = response{};
    out.magic = response_magic;
    out.version = abi_version;
    out.status_code = static_cast<i32>(code);
    out.request_id = in.request_id;
}

void list_files(const request& in, response& out) {
    reply(out, in, status::ok);
    DIR dir{};
    if (f_opendir(&dir, "") != FR_OK) { out.status_code = static_cast<i32>(status::io); return; }
    FILINFO info{};
    u32 used = 0;
    while (f_readdir(&dir, &info) == FR_OK && info.fname[0] != '\0') {
        if ((info.fattrib & AM_DIR) != 0) { continue; }
        const u32 length = text_length(info.fname, max_name);
        if (used + length + 24 >= sizeof(out.data)) { break; }
        for (u32 i = 0; i < length; ++i) { out.data[used++] = static_cast<u8>(info.fname[i]); }
        out.data[used++] = ' ';
        char digits[12];
        u32 count = 0;
        u32 size = static_cast<u32>(info.fsize);
        do { digits[count++] = static_cast<char>('0' + size % 10); size /= 10; } while (size != 0);
        while (count > 0) { out.data[used++] = static_cast<u8>(digits[--count]); }
        out.data[used++] = ' ';
        out.data[used++] = '0';
        out.data[used++] = '\n';
        ++out.value;
    }
    (void)f_closedir(&dir);
    out.length = used;
}

void handle(const request& in, response& out) {
    if (in.magic != request_magic || in.version != abi_version) {
        reply(out, in, status::invalid);
        return;
    }
    const op operation = static_cast<op>(in.operation);
    if (operation == op::ping) {
        reply(out, in, mounted && !recovery_failed ? status::ok : status::io);
        return;
    }
    if (!mounted || recovery_failed) { reply(out, in, status::io); return; }
    switch (operation) {
    case op::list:
        list_files(in, out);
        break;
    case op::stat: {
        if (!name_ok(in.name)) { reply(out, in, status::invalid); break; }
        FILINFO info{};
        const FRESULT result = f_stat(in.name, &info);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        if ((info.fattrib & AM_DIR) != 0) { reply(out, in, status::invalid); break; }
        reply(out, in, status::ok);
        out.value = info.fsize;
        out.flags = 0;
        break;
    }
    case op::open: {
        if (!name_ok(in.name) || (in.flags & read_write) == 0 ||
            (in.flags & ~u32{read_write}) != 0) { reply(out, in, status::invalid); break; }
        u32 slot = max_open;
        for (u32 i = 0; i < max_open; ++i) { if (!opens[i].used) { slot = i; break; } }
        if (slot == max_open) { reply(out, in, status::full); break; }
        BYTE mode = FA_OPEN_EXISTING;
        if ((in.flags & read_only) != 0) { mode |= FA_READ; }
        if ((in.flags & write_only) != 0) { mode |= FA_WRITE; }
        FIL file{};
        const FRESULT result = f_open(&file, in.name, mode);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        opens[slot] = open_record{};
        opens[slot].used = true;
        opens[slot].file = file;
        opens[slot].flags = in.flags;
        copy_name(opens[slot].name, in.name);
        reply(out, in, status::ok);
        out.handle = slot + 1;
        out.value = f_size(&opens[slot].file);
        break;
    }
    case op::read: {
        if (in.handle == 0 || in.handle > max_open || !opens[in.handle - 1].used) {
            reply(out, in, status::bad_handle); break;
        }
        open_record& item = opens[in.handle - 1];
        UINT read = 0;
        const UINT wanted = in.length > sizeof(out.data) ? static_cast<UINT>(sizeof(out.data)) : in.length;
        reply(out, in, status::ok);
        const FRESULT result = f_read(&item.file, out.data, wanted, &read);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        out.length = read;
        out.value = read;
        break;
    }
    case op::write: {
        if (in.handle == 0 || in.handle > max_open || !opens[in.handle - 1].used) {
            reply(out, in, status::bad_handle); break;
        }
        open_record& item = opens[in.handle - 1];
        UINT written = 0;
        UINT wanted = in.length > sizeof(in.data) ? static_cast<UINT>(sizeof(in.data)) : in.length;
        const FSIZE_t position = f_tell(&item.file);
        const u32 room = position < max_file_bytes ? static_cast<u32>(max_file_bytes - position) : 0;
        if (wanted > room) { wanted = room; }
        const FRESULT result = f_write(&item.file, in.data, wanted, &written);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        reply(out, in, status::ok);
        out.value = written;
        break;
    }
    case op::seek: {
        if (in.handle == 0 || in.handle > max_open || !opens[in.handle - 1].used ||
            in.offset > max_file_bytes) { reply(out, in, status::invalid); break; }
        const FRESULT result = f_lseek(&opens[in.handle - 1].file, static_cast<FSIZE_t>(in.offset));
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        reply(out, in, status::ok);
        out.value = in.offset;
        break;
    }
    case op::close: {
        if (in.handle == 0 || in.handle > max_open || !opens[in.handle - 1].used) {
            reply(out, in, status::bad_handle); break;
        }
        const FRESULT result = f_close(&opens[in.handle - 1].file);
        opens[in.handle - 1] = open_record{};
        reply(out, in, from_fr(result));
        break;
    }
    case op::replace_begin: {
        if (staging_active && staging_owner == in.reserved) { reply(out, in, status::busy); break; }
        if (staging_active) { staging_active = false; }
        if (!name_ok(in.name) || in.length > max_file_bytes) { reply(out, in, status::invalid); break; }
        if (!file_exists(in.name) && count_files() >= max_files) { reply(out, in, status::full); break; }
        staging_owner = in.reserved;
        copy_name(staging_name, in.name);
        staging_size = 0;
        staging_total = in.length;
        staging_active = true;
        reply(out, in, status::ok);
        out.handle = 100;
        out.value = staging_total;
        break;
    }
    case op::replace_chunk: {
        if (in.handle != 100 || !staging_active || staging_owner != in.reserved) {
            reply(out, in, status::bad_handle); break;
        }
        if (in.offset != staging_size || in.length > sizeof(in.data) ||
            staging_size + in.length > staging_total) { reply(out, in, status::invalid); break; }
        for (u32 i = 0; i < in.length; ++i) { staging[staging_size + i] = in.data[i]; }
        staging_size += in.length;
        reply(out, in, status::ok);
        out.value = staging_size;
        break;
    }
    case op::replace_commit: {
        if (in.handle != 100 || !staging_active || staging_owner != in.reserved ||
            staging_size != staging_total) { reply(out, in, status::invalid); break; }
        if (any_open(staging_name)) { reply(out, in, status::busy); break; }
        FIL file{};
        FRESULT result = f_open(&file, temp_name, FA_CREATE_ALWAYS | FA_WRITE);
        if (result != FR_OK) { reply(out, in, from_fr(result)); break; }
        UINT written = 0;
        result = f_write(&file, staging, staging_size, &written);
        if (result == FR_OK) { result = f_sync(&file); }
        (void)f_close(&file);
        if (result != FR_OK || written != staging_size) {
            (void)remove_if_present(temp_name);
            reply(out, in, result == FR_OK ? status::no_space : from_fr(result));
            break;
        }
        if (!write_journal(staging_name)) {
            (void)remove_if_present(temp_name);
            reply(out, in, status::io);
            break;
        }
        const bool target_exists = file_exists(staging_name);
        bool failed = false;
        if (target_exists) {
            (void)remove_if_present(backup_name);
            if (f_rename(staging_name, backup_name) != FR_OK) { failed = true; }
        }
        if (!failed && f_rename(temp_name, staging_name) != FR_OK) {
            failed = true;
            if (target_exists && f_rename(backup_name, staging_name) != FR_OK) {
                recovery_failed = true;
            }
        }
        if (failed) {
            (void)remove_if_present(temp_name);
            if (!recovery_failed) {
                (void)f_unlink(journal_name);
                (void)remove_if_present(backup_name);
            }
            reply(out, in, status::io);
            break;
        }
        const FRESULT synced = disk_ioctl(0, CTRL_SYNC, nullptr) == RES_OK ? FR_OK : FR_DISK_ERR;
        if (synced != FR_OK) {
            recovery_failed = true;
            reply(out, in, status::io);
            break;
        }
        (void)remove_if_present(backup_name);
        (void)f_unlink(journal_name);
        (void)disk_ioctl(0, CTRL_SYNC, nullptr);
        staging_active = false;
        reply(out, in, status::ok);
        out.value = staging_size;
        break;
    }
    case op::replace_abort:
        if (in.handle != 100 || !staging_active || staging_owner != in.reserved) {
            reply(out, in, status::bad_handle); break;
        }
        staging_active = false;
        reply(out, in, status::ok);
        break;
    case op::sync: {
        status code = status::ok;
        for (auto& item : opens) {
            if (!item.used || (item.flags & write_only) == 0) { continue; }
            const FRESULT synced = f_sync(&item.file);
            if (synced != FR_OK) { code = from_fr(synced); break; }
        }
        if (code == status::ok && disk_ioctl(0, CTRL_SYNC, nullptr) != RES_OK) {
            code = status::io;
        }
        reply(out, in, code);
        break;
    }
    case op::remove: {
        if (!name_ok(in.name)) { reply(out, in, status::invalid); break; }
        if (any_open(in.name)) { reply(out, in, status::busy); break; }
        const FRESULT result = f_unlink(in.name);
        reply(out, in, from_fr(result));
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
    u32 send_handle = 0;
    u32 recv_handle = 0;
    if (sdk::ipc_handles(send_handle, recv_handle) < 0 ||
        send_handle == 0 || recv_handle == 0) {
        sdk::exit(1);
    }
    const FRESULT result = f_mount(&fs, "", 1);
    mounted = result == FR_OK;
    if (mounted) { recover(); }
    for (;;) {
        file::request request{};
        const i64 received = sdk::ipc_recv(recv_handle, &request, sizeof(request));
        if (received <= 0) { sdk::yield(); continue; }
        file::response response{};
        if (received != static_cast<i64>(sizeof(request))) {
            response.magic = file::response_magic;
            response.version = file::abi_version;
            response.status_code = static_cast<i32>(file::status::invalid);
        } else {
            handle(request, response);
        }
        while (sdk::ipc_send(send_handle, &response, sizeof(response)) < 0) {
            sdk::yield();
        }
    }
}
