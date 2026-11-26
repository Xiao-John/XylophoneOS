// SPDX-License-Identifier: Apache-2.0
// Production glibc, SDK, files and FatFs; only kernel transport is substituted.
#define xos_file_fixture_external_syscall
#define main original_file_semantics_main
#define DIR fat_directory
#include "../file_semantics/file_semantics.cpp"
#undef DIR
#undef main
#include "xos_file_runtime.h"
#include "xos_file_positioned.h"
#include "xos_file_directory.h"
#include <xos/file_client.hpp>
#include <cerrno>
#include <fcntl.h>
#include <set>

extern "C" { const void* __xos_startup = nullptr; }
static xos::file::response pending;
static bool has_pending;

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64) {
    if (number == 6) return 10;
    if (number == sys_ipc_handles) {
        auto* handles = reinterpret_cast<u32*>(first);
        handles[0] = 100; handles[1] = 101;
    } else if (number == sys_process_guard) {
        *reinterpret_cast<process_guard_info*>(second) = kernel_guard;
    } else if (number == sys_file_session) {
        if (first >= file::max_sessions) return -2;
        *reinterpret_cast<file_session_info*>(second) = kernel_sessions[first];
    }
    return 0;
}
}
extern "C" int __xos_file_test_startup_range(xos_u64, xos_u64) { return 0; }
extern "C" xos_i64 __xos_wait_word(xos_u32*, xos_u32, xos_u64) { std::abort(); }
extern "C" xos_i64 __xos_wake_word(xos_u32*, xos_u32) { return 0; }
extern "C" long __xos_file_test_trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third) {
    if (number == 6) return 10;
    if (number == 22) {
        auto* handles = reinterpret_cast<xos_u32*>(first);
        handles[0] = 100; handles[1] = 101;
        return 0;
    }
    if (number == 46) return 100;
    if (number == 4) {
        require(first == 100 && third == 4096 && !has_pending, "request transport");
        handle(*reinterpret_cast<const xos::file::request*>(second), pending, sessions[0], 0);
        has_pending = true;
        return 0;
    }
    if (number == 5) {
        require(first == 101 && third == 4096 && has_pending, "response transport");
        std::memcpy(reinterpret_cast<void*>(second), &pending, sizeof(pending));
        has_pending = false;
        return 4096;
    }
    if (number == 13) return 0;
    std::abort();
}

static int opened(const char* path, int flags = O_RDWR) {
    long result = __xos_file_open(path, flags);
    require(result >= 0, path);
    return static_cast<int>(result);
}
static void passed(const char* name) { ++checks; std::printf("PASS files_extra %s\n", name); }
static std::set<std::string> names(DIR* directory, unsigned long expected_self = 0) {
    std::set<std::string> result;
    struct dirent* item = nullptr;
    long code;
    while ((code = __xos_directory_read(directory, &item)) == 1) {
        require(item != nullptr && item->d_ino != 0, "real directory identity");
        require(result.insert(item->d_name).second, "no repeated entry");
        if (!std::strcmp(item->d_name, ".") && expected_self)
            require(item->d_ino == expected_self && item->d_type == DT_DIR, "dot identity matches fstat");
    }
    require(code == 0 && item == nullptr, "clean directory EOF");
    return result;
}

int main(int argc, char** argv) {
    require(argc == 2, "private image argument");
    FILE* image = std::fopen(argv[1], "rb");
    require(image != nullptr, "private image open");
    std::fseek(image, 0, SEEK_END);
    original.resize(static_cast<size_t>(std::ftell(image)));
    std::rewind(image);
    require(std::fread(original.data(), 1, original.size(), image) == original.size(), "image read");
    std::fclose(image);
    reset_media();
    sessions[0].pid = 10;
    int fd = opened("/positioned", O_CREAT | O_RDWR);
    require(__xos_file_write(fd, "abcdefgh", 8) == 8, "seed file");
    int alias = static_cast<int>(__xos_file_dup(fd, 0, 0, 0));
    require(alias >= 0 && __xos_file_seek(fd, 3, SEEK_SET) == 3, "shared cursor");
    char data[8192]{};
    require(__xos_file_pwrite(alias, "XY", 2, 0) == 2, "positioned write");
    require(__xos_file_pread(alias, data, 8, 0) == 8 && !std::memcmp(data, "XYcdefgh", 8), "positioned read");
    require(__xos_file_seek(fd, 0, SEEK_CUR) == 3, "shared cursor unchanged");
    require(__xos_file_read(fd, data, 1) == 1 && data[0] == 'd', "ordinary read retains cursor");
    passed("dup_position_unchanged");

    xos_file_lease lease{};
    require(__xos_file_lease_acquire(fd, -1, &lease) == 0, "source lease");
    sessions[1].pid = 11; sessions[1].parent_pid = 10;
    request transfer = make_request(op::transfer);
    transfer.handle = lease.handle; transfer.offset = 11;
    response child = call(sessions[0], transfer);
    require(child.status_code == 0 && child.handle != 0, "authenticated child transfer");
    request positioned = make_request(op::write_at);
    positioned.handle = child.handle; positioned.offset = 1; positioned.length = 1;
    positioned.data[0] = 'Z';
    require(call(sessions[1], positioned).value == 1, "child positioned write");
    require(__xos_file_seek(fd, 0, SEEK_CUR) == 4, "child cannot move shared cursor");
    response ordinary = read_handle(sessions[1], child.handle, 1);
    require(ordinary.length == 1 && ordinary.data[0] == 'e' && __xos_file_seek(fd, 0, SEEK_CUR) == 5,
            "child ordinary read shares cursor");
    require(close_handle(sessions[1], child.handle).status_code == 0, "child handle reclaimed");
    require(__xos_file_lease_release(&lease) == 0, "source lease released");
    passed("cross_session_shared_description");

    int append = opened("/positioned", O_RDWR | O_APPEND);
    require(__xos_file_seek(append, 2, SEEK_SET) == 2, "append saved cursor");
    require(__xos_file_pwrite(append, "P", 1, 0) == 1 && __xos_file_seek(append, 0, SEEK_CUR) == 2,
            "pwrite explicit offset ignores append");
    require(__xos_file_write(append, "!", 1) == 1 && __xos_file_seek(append, 0, SEEK_CUR) == 9,
            "ordinary write still appends");
    require(__xos_file_close(append) == 0, "append close");
    require(__xos_file_pwrite(fd, "x", 1, 4096) == 1, "sparse positioned write");
    require(__xos_file_pread(fd, data, sizeof(data), 9) == 3798, "bounded positioned read");
    for (unsigned i = 0; i < 3798; ++i) require(data[i] == 0, "hole cleared");
    require(__xos_file_seek(fd, 0, SEEK_CUR) == 5, "hole leaves offset");
    passed("append_and_sparse_zeros");

    require(__xos_file_truncate(fd, 8) == 0, "fault fixture length");
    write_calls = 0; write_fail_nth = 1;
    require(__xos_file_pwrite(fd, "q", 1, 4096) == -ENOSPC, "failed hole reports no space");
    struct stat stat{};
    require(__xos_file_stat(fd, nullptr, &stat) == 0 && stat.st_size == 8 &&
            __xos_file_seek(fd, 0, SEEK_CUR) == 5, "failed hole rolls back length and offset");
    write_fault_after = 2;
    require(__xos_file_pwrite(fd, "1234", 4, 0) == 2 && __xos_file_seek(fd, 0, SEEK_CUR) == 5,
            "partial write retains offset");
    read_fault_after = 1;
    require(__xos_file_pread(fd, data, 4, 0) == 1 && data[0] == '1', "partial read progress");
    require(__xos_file_pwrite(fd, nullptr, 0, 100) == 0 &&
            __xos_file_stat(fd, nullptr, &stat) == 0 && stat.st_size == 8, "zero write no growth");
    require(__xos_file_pread(fd, data, 1, -1) == -EINVAL &&
            __xos_file_pwrite(fd, data, 1, 0x100000000L) == -EOVERFLOW, "offset bounds");
    require(__xos_file_close(alias) == 0 && __xos_file_close(fd) == 0, "regular fds close");
    passed("short_io_fault_rollback_bounds");

    xos::file::client sdk;
    require(sdk.init(), "SDK session");
    u32 handle = 0, size = 0, version = 0;
    require(sdk.open("/positioned", read_write, handle, size, version) == 0, "SDK open");
    require(sdk.seek(handle, 3) == 3 && sdk.write_at(handle, "sdk", 3, 0) == 3 &&
            sdk.read_at(handle, data, 3, 0) == 3 && !std::memcmp(data, "sdk", 3), "native SDK positioned calls");
    require(sdk.seek(handle, 0, seek_current) == 3 && sdk.close(handle) == 0, "SDK shared exchange offset");
    passed("native_sdk_same_session_exchange");

    require(__xos_file_path_op("/entries", 15) == 0, "directory create");
    for (int i = 0; i < 96; ++i) {
        char path[80]; std::snprintf(path, sizeof(path), "/entries/file_%03d_long_utf8_目录", i);
        int entry = opened(path, O_CREAT | O_RDWR);
        require(__xos_file_close(entry) == 0, "directory fixture entry close");
    }
    fd = opened("/entries", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    require(__xos_file_stat(fd, nullptr, &stat) == 0, "directory stat");
    DIR* directory = nullptr;
    require(__xos_directory_open(fd, &directory) == 0, "directory stream");
    auto all = names(directory, stat.st_ino);
    require(all.size() == 98 && all.contains(".") && all.contains(".."), "multi page UTF8 list");
    require(__xos_directory_seek(directory, 0) == 0, "rewind");
    struct dirent* entry = nullptr;
    require(__xos_directory_read(directory, &entry) == 1 && !std::strcmp(entry->d_name, "."), "rewound dot");
    long cookie = __xos_directory_tell(directory);
    require(__xos_directory_read(directory, &entry) == 1, "next after cookie");
    std::string expected(entry->d_name);
    require(__xos_directory_seek(directory, cookie) == 0 && __xos_directory_read(directory, &entry) == 1 &&
            expected == entry->d_name, "seek cookie");
    require(rename_path(sessions[0], "/entries", "/renamed").status_code == 0, "rename held directory");
    require(__xos_directory_seek(directory, 0) == 0 && names(directory, stat.st_ino) == all,
            "directory follows renamed object");
    require(__xos_directory_close(directory) == 0, "directory close");
    passed("directory_identity_pagination_cookie_rename");

    require(__xos_file_path_op("/empty", 15) == 0, "detached directory fixture");
    fd = opened("/empty", O_RDONLY | O_DIRECTORY);
    require(__xos_file_stat(fd, nullptr, &stat) == 0 && __xos_directory_open(fd, &directory) == 0, "old directory hold");
    request remove = make_request(op::remove); set_name(remove, "/empty"); remove.flags = allow_directory;
    require(call(sessions[0], remove).status_code == 0 && __xos_file_path_op("/empty", 15) == 0, "unlink and recreate");
    require(names(directory, stat.st_ino).size() == 2, "detached stream remains old empty identity");
    require(__xos_directory_close(directory) == 0, "detached close reclaims");
    for (int i = 0; i < 64; ++i) {
        fd = opened("/renamed", O_RDONLY | O_DIRECTORY);
        require(__xos_directory_open(fd, &directory) == 0 && __xos_directory_close(directory) == 0,
                "directory object slots reusable");
    }
    passed("deleted_directory_identity_and_reclamation");

    close_session(sessions[0]); close_session(sessions[1]); retry_description_cleanup();
    for (const auto& description : descriptions) require(!description.used, "all descriptions reclaimed");
    for (const auto& object : file_objects) require(!object.used, "all objects reclaimed");
    require(!recovery_failed, "recovery gate stays healthy");
    passed("all_service_resources_reclaimed");
    std::printf("PASS %d files_extra real integration groups\n", checks);
}
