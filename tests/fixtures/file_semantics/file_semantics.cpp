// SPDX-License-Identifier: Apache-2.0
// Exercise the production file service against real FatFs with a private
// memory image. Covers POSIX offset/truncate/rename/transfer semantics and
// short read/write progress. This is a host API-boundary test, not a guest
// end-to-end acceptance.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include "ff.h"
#include "diskio.h"

// Injected failures target only the operation under test. These are defined
// before the macro redirect so their own calls reach real FatFs.
int write_fault_after = -1;   // >= 0: short-write this many bytes then error.
int write_short_by = -1;      // >= 0: report success but write fewer bytes.
int write_fail_nth = -1;      // >= 0: the Nth armed f_write reports a
                              // zero-byte FR_OK short write (disk full).
int write_calls = 0;
int read_fault_after = -1;    // >= 0: read this many bytes then error.

int rename_fault_nth = -1;
int rename_fault_nth2 = -1;
int rename_calls = 0;

FRESULT injected_rename(const char* old_path, const char* new_path) {
    ++rename_calls;
    if (rename_calls == rename_fault_nth || rename_calls == rename_fault_nth2) {
        return FR_DISK_ERR;
    }
    return f_rename(old_path, new_path);
}

FRESULT injected_read(FIL* file, void* buffer, UINT length, UINT* got) {
    if (read_fault_after >= 0) {
        const UINT partial = static_cast<UINT>(read_fault_after);
        read_fault_after = -1;
        FRESULT result = f_read(file, buffer, partial, got);
        if (result == FR_OK) { result = FR_DISK_ERR; }
        return result;
    }
    return f_read(file, buffer, length, got);
}

FRESULT injected_write(FIL* file, const void* buffer, UINT length, UINT* written) {
    if (write_fail_nth >= 0 && ++write_calls == write_fail_nth) {
        // Model a full medium: FatFs reports FR_OK with zero bytes written.
        write_fail_nth = -1;
        *written = 0;
        return FR_OK;
    }
    if (write_fault_after >= 0) {
        const UINT partial = static_cast<UINT>(write_fault_after);
        write_fault_after = -1;
        FRESULT result = f_write(file, buffer, partial, written);
        if (result == FR_OK) { result = FR_DISK_ERR; }
        return result;
    }
    if (write_short_by >= 0) {
        const UINT partial = length > static_cast<UINT>(write_short_by)
                                 ? length - static_cast<UINT>(write_short_by) : 0;
        write_short_by = -1;
        return f_write(file, buffer, partial, written);
    }
    return f_write(file, buffer, length, written);
}

#define f_read injected_read
#define f_write injected_write
#define f_rename injected_rename
#include "../../../src/user/services/files.cpp"
#undef f_read
#undef f_write
#undef f_rename

namespace xos::sdk { i64 syscall(u64, u64, u64, u64) { return 0; } }

namespace {
using namespace xos;
using namespace xos::file;
std::vector<unsigned char> original, media;
int checks = 0;

void require(bool value, const char* why) {
    if (!value) { std::fprintf(stderr, "FAIL %s\n", why); std::exit(1); }
}

request make_request(op operation) {
    request in{};
    in.magic = request_magic;
    in.version = abi_version;
    in.operation = static_cast<u16>(operation);
    in.request_id = 1;
    return in;
}

void set_name(request& in, const char* name) {
    const u32 length = static_cast<u32>(std::strlen(name));
    std::memcpy(in.name, name, length);
    in.name_length = length;
}

response call(client_session& client, const request& in) {
    response out{};
    handle(in, out, client, 0);
    return out;
}

response open_path(client_session& client, const char* name, u32 flags) {
    request in = make_request(op::open);
    set_name(in, name);
    in.flags = flags;
    return call(client, in);
}

response close_handle(client_session& client, u32 handle) {
    request in = make_request(op::close);
    in.handle = handle;
    return call(client, in);
}

response read_handle(client_session& client, u32 handle, u32 length) {
    request in = make_request(op::read);
    in.handle = handle;
    in.length = length;
    return call(client, in);
}

response write_handle(client_session& client, u32 handle, const void* data, u32 length) {
    request in = make_request(op::write);
    in.handle = handle;
    in.length = length;
    std::memcpy(in.data, data, length);
    return call(client, in);
}

response seek_handle(client_session& client, u32 handle, u64 offset, u32 origin) {
    request in = make_request(op::seek);
    in.handle = handle;
    in.offset = offset;
    in.flags = origin;
    return call(client, in);
}

response truncate_handle(client_session& client, u32 handle, u32 length) {
    request in = make_request(op::truncate);
    in.handle = handle;
    in.offset = length;
    return call(client, in);
}

response fstat_handle(client_session& client, u32 handle) {
    request in = make_request(op::fstat);
    in.handle = handle;
    return call(client, in);
}

response rename_path(client_session& client, const char* from, const char* to) {
    request in = make_request(op::rename);
    set_name(in, from);
    in.length = static_cast<u32>(std::strlen(to));
    std::memcpy(in.data, to, in.length);
    return call(client, in);
}

response mkdir_path(client_session& client, const char* name) {
    request in = make_request(op::mkdir);
    set_name(in, name);
    return call(client, in);
}

std::string read_file(const char* path) {
    FIL file{};
    if (f_open(&file, path, FA_READ) != FR_OK) { return "<absent>"; }
    char bytes[512]{};
    UINT got = 0;
    require(f_read(&file, bytes, sizeof(bytes), &got) == FR_OK, "inspect read");
    require(f_close(&file) == FR_OK, "inspect close");
    return std::string(bytes, got);
}

void reset_media() {
    f_mount(nullptr, "", 0);
    media = original;
    fs = FATFS{};
    mounted = true;
    recovery_failed = false;
    require(f_mount(&fs, "", 1) == FR_OK, "fixture mount");
    for (auto& session : sessions) { session = client_session{}; }
    for (auto& description : descriptions) { description = open_description{}; }
    generations[0] = 0;
    next_anonymous_serial = 0;
}

void seed_file(const char* path, const void* data, UINT length) {
    FIL file{};
    UINT written = 0;
    require(f_open(&file, path, FA_CREATE_ALWAYS | FA_WRITE) == FR_OK, "seed open");
    require(f_write(&file, data, length, &written) == FR_OK && written == length, "seed write");
    require(f_close(&file) == FR_OK, "seed close");
}
}

int main(int argc, char** argv) {
    require(argc == 2, "image argument");
    FILE* image = std::fopen(argv[1], "rb");
    require(image != nullptr, "fixture image");
    std::fseek(image, 0, SEEK_END);
    original.resize(static_cast<size_t>(std::ftell(image)));
    std::rewind(image);
    require(std::fread(original.data(), 1, original.size(), image) == original.size(),
            "fixture image read");
    std::fclose(image);

    client_session client{};
    client.pid = 10;
    client.parent_pid = 5;

    // 1. O_TRUNC/O_APPEND without O_CREAT must not create a new file.
    reset_media();
    require(open_path(client, "missing.txt", xos::file::write_only | xos::file::open_truncate).status_code ==
            static_cast<i32>(status::not_found), "truncate without create");
    require(open_path(client, "missing.txt", xos::file::write_only | xos::file::open_append).status_code ==
            static_cast<i32>(status::not_found), "append without create");
    require(read_file("missing.txt") == "<absent>", "no file created");
    ++checks;

    // 2. O_TRUNC without O_CREAT truncates an existing file.
    seed_file("existing.txt", "abcdef", 6);
    response opened = open_path(client, "existing.txt", xos::file::write_only | xos::file::open_truncate);
    require(opened.status_code == static_cast<i32>(status::ok), "truncate existing open");
    require(fstat_handle(client, opened.handle).value == 0, "truncate existing size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "truncate close");
    require(read_file("existing.txt") == "", "truncate existing content");
    ++checks;

    // 3. ftruncate preserves the offset, including a shared description.
    seed_file("offset.txt", "0123456789", 10);
    opened = open_path(client, "offset.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "offset open");
    require(seek_handle(client, opened.handle, 2, xos::file::seek_set).value == 2, "seek set 2");
    require(truncate_handle(client, opened.handle, 4).status_code == static_cast<i32>(status::ok), "truncate shrink");
    require(seek_handle(client, opened.handle, 0, xos::file::seek_current).value == 2, "offset preserved");
    require(fstat_handle(client, opened.handle).value == 4, "shrink size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "offset close");
    ++checks;

    // 4. Growing ftruncate zero-fills instead of exposing reused clusters.
    seed_file("grow.txt", "ABCD", 4);
    opened = open_path(client, "grow.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "grow open");
    require(truncate_handle(client, opened.handle, 12).status_code == static_cast<i32>(status::ok), "grow truncate");
    require(fstat_handle(client, opened.handle).value == 12, "grow size");
    require(seek_handle(client, opened.handle, 0, xos::file::seek_set).value == 0, "grow rewind");
    response grown = read_handle(client, opened.handle, 12);
    require(grown.status_code == static_cast<i32>(status::ok) && grown.length == 12, "grow read");
    require(std::memcmp(grown.data, "ABCD\0\0\0\0\0\0\0\0", 12) == 0, "grow zeros");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "grow close");
    ++checks;

    // 5. lseek past EOF must not change the file length; a later write fills
    //    the gap with zeros.
    seed_file("hole.txt", "xy", 2);
    opened = open_path(client, "hole.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "hole open");
    require(seek_handle(client, opened.handle, 8, xos::file::seek_set).value == 8, "hole seek");
    require(fstat_handle(client, opened.handle).value == 2, "seek does not extend");
    require(write_handle(client, opened.handle, "Z", 1).value == 1, "hole write");
    require(fstat_handle(client, opened.handle).value == 9, "hole size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "hole close");
    require(read_file("hole.txt") == std::string("xy\0\0\0\0\0\0Z", 9), "hole zeros");
    ++checks;

    // 6. rename replaces an existing target and leaves no staging material.
    seed_file("source.txt", "new", 3);
    seed_file("target.txt", "old", 3);
    require(rename_path(client, "source.txt", "target.txt").status_code == static_cast<i32>(status::ok),
            "rename replace");
    require(read_file("target.txt") == "new", "rename target content");
    require(read_file("source.txt") == "<absent>", "rename source gone");
    require(read_file(backup_name) == "<absent>", "rename backup cleaned");
    require(read_file(journal_name) == "<absent>", "rename journal cleaned");
    ++checks;

    // 7. A directory cannot be renamed into its own descendant.
    require(mkdir_path(client, "a").status_code == static_cast<i32>(status::ok), "mkdir a");
    require(mkdir_path(client, "a/b").status_code == static_cast<i32>(status::ok), "mkdir a/b");
    seed_file("a/file", "keep", 4);
    require(rename_path(client, "a", "a/b/new").status_code == static_cast<i32>(status::invalid),
            "reject descendant rename");
    FILINFO info{};
    require(f_stat("a", &info) == FR_OK && (info.fattrib & AM_DIR) != 0, "source tree intact");
    require(f_stat("a/b", &info) == FR_OK && (info.fattrib & AM_DIR) != 0, "child tree intact");
    require(read_file("a/file") == "keep", "descendant content intact");
    ++checks;

    // 8. Handle transfer requires the target's kernel-authenticated parent.
    seed_file("transfer.txt", "data", 4);
    opened = open_path(client, "transfer.txt", xos::file::read_only);
    require(opened.status_code == static_cast<i32>(status::ok), "transfer open");
    sessions[1] = client_session{};
    sessions[1].pid = 20;
    sessions[1].parent_pid = 99;
    request move = make_request(op::transfer);
    move.handle = opened.handle;
    move.offset = 20;
    require(call(client, move).status_code == static_cast<i32>(status::invalid), "reject unrelated target");
    sessions[1].parent_pid = 10;
    require(call(client, move).status_code == static_cast<i32>(status::ok), "allow child target");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "transfer close");
    ++checks;

    // 9. Partial write progress is reported, and the offset advances.
    seed_file("partial.txt", "0123456789", 10);
    opened = open_path(client, "partial.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "partial open");
    write_fault_after = 4;
    response partial = write_handle(client, opened.handle, "abcd", 4);
    require(partial.status_code == static_cast<i32>(status::ok) && partial.value == 4,
            "partial write counted");
    require(seek_handle(client, opened.handle, 0, xos::file::seek_current).value == 4,
            "partial write offset");
    ++checks;

    // 10. Partial read progress is returned instead of a bare error.
    read_fault_after = 3;
    response short_read = read_handle(client, opened.handle, 4);
    require(short_read.status_code == static_cast<i32>(status::ok) && short_read.length == 3,
            "partial read counted");
    require(seek_handle(client, opened.handle, 0, xos::file::seek_current).value == 7,
            "partial read offset");
    read_fault_after = 0;
    response failed = read_handle(client, opened.handle, 4);
    require(failed.status_code == static_cast<i32>(status::io), "zero-progress read fails");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "partial close");
    ++checks;

    // 11. A failed growth is rolled back instead of reporting success.
    seed_file("rollback.txt", "0123", 4);
    opened = open_path(client, "rollback.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "rollback open");
    write_short_by = 512;
    require(truncate_handle(client, opened.handle, 4096).status_code == static_cast<i32>(status::no_space),
            "short growth reports no_space");
    require(fstat_handle(client, opened.handle).value == 4, "growth rollback size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "rollback close");
    require(read_file("rollback.txt") == "0123", "growth rollback content");
    ++checks;

    // 12. Case-only rename updates the stored FAT name instead of no-op.
    //     f_stat backfills the requested spelling, so only a directory read
    //     proves the stored dirent actually changed.
    reset_media();
    seed_file("Case.txt", "x", 1);
    require(rename_path(client, "Case.txt", "case.txt").status_code == static_cast<i32>(status::ok),
            "case rename");
    DIR case_dir{};
    FILINFO case_entry{};
    bool saw_new_spelling = false;
    bool saw_old_spelling = false;
    require(f_opendir(&case_dir, "/") == FR_OK, "case rename opendir");
    for (;;) {
        const FRESULT listed = f_readdir(&case_dir, &case_entry);
        require(listed == FR_OK, "case rename readdir");
        if (case_entry.fname[0] == '\0') { break; }
        if (std::strcmp(case_entry.fname, "case.txt") == 0) { saw_new_spelling = true; }
        if (std::strcmp(case_entry.fname, "Case.txt") == 0) { saw_old_spelling = true; }
    }
    f_closedir(&case_dir);
    require(saw_new_spelling && !saw_old_spelling, "case rename stored dirent");
    ++checks;

    // 13. A failed gap fill must not leave the file extended.
    reset_media();
    seed_file("gaproll.txt", "0123", 4);
    opened = open_path(client, "gaproll.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "gap open");
    require(seek_handle(client, opened.handle, 1024, xos::file::seek_set).value == 1024, "gap seek");
    write_short_by = 512;
    require(write_handle(client, opened.handle, "Z", 1).status_code == static_cast<i32>(status::no_space),
            "gap short write");
    require(fstat_handle(client, opened.handle).value == 4, "gap rollback size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok), "gap close");
    require(read_file("gaproll.txt") == "0123", "gap rollback content");
    ++checks;

    // 14. A short journal write must not publish a truncated marker.
    reset_media();
    seed_file("jsrc.txt", "new", 3);
    seed_file("jdst.txt", "old", 3);
    write_short_by = 512;
    require(rename_path(client, "jsrc.txt", "jdst.txt").status_code == static_cast<i32>(status::io),
            "journal short write");
    require(read_file("jsrc.txt") == "new" && read_file("jdst.txt") == "old", "journal unchanged files");
    require(read_file(journal_name) == "<absent>" && read_file(journal_temp_name) == "<absent>",
            "journal cleaned");
    ++checks;

    // 15. If restoring the backup also fails, keep the journal so boot
    //     recovery can restore the old target instead of stranding XOSBAK.TMP.
    reset_media();
    seed_file("rsrc.txt", "new", 3);
    seed_file("rdst.txt", "old", 3);
    rename_calls = 0;
    rename_fault_nth = 3;
    rename_fault_nth2 = 4;
    require(rename_path(client, "rsrc.txt", "rdst.txt").status_code == static_cast<i32>(status::io),
            "rename double failure");
    require(recovery_failed, "rename double failure gate");
    require(read_file(journal_name).rfind("rdst.txt", 0) == 0, "journal retained");
    require(read_file(backup_name) == "old", "backup retained");
    require(read_file("rdst.txt") == "<absent>", "target absent before recovery");
    rename_fault_nth = -1;
    rename_fault_nth2 = -1;
    recovery_failed = false;  // simulate a fresh service process
    recover();
    require(!recovery_failed, "rename recovery gate");
    require(read_file("rdst.txt") == "old", "rename recovered target");
    require(read_file(journal_name) == "<absent>" && read_file(backup_name) == "<absent>",
            "rename recovery cleanup");
    ++checks;

    // 16. A zero-byte write past EOF is a POSIX no-op: no extension and no
    //     offset change, even though the handle logically sits past EOF.
    reset_media();
    seed_file("zero.txt", "01", 2);
    opened = open_path(client, "zero.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "zero write open");
    require(seek_handle(client, opened.handle, 9, xos::file::seek_set).value == 9, "zero write seek");
    require(write_handle(client, opened.handle, "", 0).status_code == static_cast<i32>(status::ok),
            "zero write ok");
    require(fstat_handle(client, opened.handle).value == 2, "zero write no extend");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok),
            "zero write close");
    require(read_file("zero.txt") == "01", "zero write content");
    ++checks;

    // 17. When the hole fill succeeds but the data write then reports zero
    //     bytes (full medium), the service must report no_space and undo the
    //     extension instead of leaving a longer file behind.
    reset_media();
    seed_file("fullhole.txt", "0123", 4);
    opened = open_path(client, "fullhole.txt", xos::file::read_write);
    require(opened.status_code == static_cast<i32>(status::ok), "fullhole open");
    require(seek_handle(client, opened.handle, 1024, xos::file::seek_set).value == 1024, "fullhole seek");
    write_calls = 0;
    write_fail_nth = 3;  // grow_with_zeros writes 512+508 zero bytes first.
    require(write_handle(client, opened.handle, "Z", 1).status_code ==
            static_cast<i32>(status::no_space), "fullhole zero-byte write");
    require(fstat_handle(client, opened.handle).value == 4, "fullhole rollback size");
    require(close_handle(client, opened.handle).status_code == static_cast<i32>(status::ok),
            "fullhole close");
    write_fail_nth = -1;
    require(read_file("fullhole.txt") == "0123", "fullhole rollback content");
    ++checks;

    // 18. rm must not delete an empty directory: op::remove refuses it and the
    //     directory itself stays on disk.
    reset_media();
    require(mkdir_path(client, "rm_empty").status_code == static_cast<i32>(status::ok),
            "mkdir rm_empty");
    request removal = make_request(op::remove);
    set_name(removal, "rm_empty");
    require(call(client, removal).status_code == static_cast<i32>(status::invalid),
            "rm empty directory refused");
    require(f_stat("rm_empty", &info) == FR_OK && (info.fattrib & AM_DIR) != 0,
            "empty directory survives rm");
    ++checks;

    // 19. The same refusal for a non-empty directory must leave its contents.
    require(mkdir_path(client, "rm_full").status_code == static_cast<i32>(status::ok),
            "mkdir rm_full");
    seed_file("rm_full/child.txt", "keep", 4);
    removal = make_request(op::remove);
    set_name(removal, "rm_full");
    require(call(client, removal).status_code == static_cast<i32>(status::invalid),
            "rm non-empty directory refused");
    require(f_stat("rm_full", &info) == FR_OK && (info.fattrib & AM_DIR) != 0,
            "non-empty directory survives rm");
    require(read_file("rm_full/child.txt") == "keep", "directory content intact");
    ++checks;

    // 20. allow_directory restores rmdir semantics: opting in deletes an empty
    //     directory.
    require(mkdir_path(client, "rmdir_ok").status_code == static_cast<i32>(status::ok),
            "mkdir rmdir_ok");
    removal = make_request(op::remove);
    set_name(removal, "rmdir_ok");
    removal.flags = allow_directory;
    require(call(client, removal).status_code == static_cast<i32>(status::ok),
            "allow_directory removes empty directory");
    require(f_stat("rmdir_ok", &info) != FR_OK, "opted-in directory is gone");
    ++checks;

    // 21. The opt-in weakens nothing else: a non-empty directory is still
    //     refused (FatFs FR_DENIED) and keeps its contents.
    require(mkdir_path(client, "rmdir_full").status_code == static_cast<i32>(status::ok),
            "mkdir rmdir_full");
    seed_file("rmdir_full/child.txt", "keep", 4);
    removal = make_request(op::remove);
    set_name(removal, "rmdir_full");
    removal.flags = allow_directory;
    require(call(client, removal).status_code == static_cast<i32>(status::invalid),
            "allow_directory still refuses non-empty directory");
    require(f_stat("rmdir_full", &info) == FR_OK && (info.fattrib & AM_DIR) != 0,
            "non-empty directory survives opt-in");
    require(read_file("rmdir_full/child.txt") == "keep", "opted-in content intact");
    ++checks;

    std::printf("FILE_SEMANTICS_CASES_PASSED=%d\n", checks);
    return 0;
}

// FatFs disk backend over the private memory image.
extern "C" DSTATUS disk_initialize(BYTE p) { return p ? STA_NOINIT : 0; }
extern "C" DSTATUS disk_status(BYTE p) { return disk_initialize(p); }
extern "C" DRESULT disk_read(BYTE p, BYTE* buffer, LBA_t sector, UINT count) {
    if (p || sector >= media.size() / 512 || count > media.size() / 512 - sector) { return RES_PARERR; }
    std::memcpy(buffer, media.data() + sector * 512, static_cast<size_t>(count) * 512);
    return RES_OK;
}
extern "C" DRESULT disk_write(BYTE p, const BYTE* buffer, LBA_t sector, UINT count) {
    if (p || sector >= media.size() / 512 || count > media.size() / 512 - sector) { return RES_PARERR; }
    std::memcpy(media.data() + sector * 512, buffer, static_cast<size_t>(count) * 512);
    return RES_OK;
}
extern "C" DRESULT disk_ioctl(BYTE p, BYTE command, void* buffer) {
    if (p) { return RES_PARERR; }
    if (command == CTRL_SYNC) { return RES_OK; }
    if (command == GET_SECTOR_COUNT) {
        *static_cast<LBA_t*>(buffer) = media.size() / 512; return RES_OK;
    }
    if (command == GET_SECTOR_SIZE) { *static_cast<WORD*>(buffer) = 512; return RES_OK; }
    if (command == GET_BLOCK_SIZE) { *static_cast<DWORD*>(buffer) = 1; return RES_OK; }
    return RES_PARERR;
}
