// SPDX-License-Identifier: Apache-2.0
// The production glibc runtime talks to production files.cpp and FatFs.
#include "xos_file_runtime.h"
#include <xos/file_abi.hpp>
#include <xos/sdk.hpp>
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <initializer_list>

extern "C" void identity_service_mount(const char*);
extern "C" void identity_service_request(const xos::file::request*, xos::file::response*);
extern "C" void identity_service_finished();
extern "C" xos::i64 identity_service_block(xos::u64, xos::u64, xos::u64, xos::u64);
extern int write_fault_after, write_short_by, write_fail_nth, write_calls, read_fault_after;
extern "C" { const void *__xos_startup = nullptr; }
static xos::file::response pending;
static bool has_pending;
static unsigned int cases;
static unsigned int block_reads;

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == sys_process_guard) {
        *reinterpret_cast<process_guard_info*>(second) = {};
    }
    if (number == sys_block_info || number == sys_block_read) {
        if (number == sys_block_read) ++block_reads;
        return identity_service_block(number, first, second, third);
    }
    return 0;
}
}
extern "C" int __xos_file_test_startup_range(xos_u64, xos_u64) { return 0; }
extern "C" xos_i64 __xos_wait_word(xos_u32*, xos_u32, xos_u64) { std::abort(); }
extern "C" xos_i64 __xos_wake_word(xos_u32*, xos_u32) { return 0; }
extern "C" long __xos_file_test_trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third) {
    if (number == 22) {
        auto* handles = reinterpret_cast<xos_u32*>(first);
        handles[0] = 100; handles[1] = 101;
        return 0;
    }
    if (number == 46) return 100;
    if (number == 4) {
        assert(first == 100 && third == 4096 && !has_pending);
        identity_service_request(reinterpret_cast<const xos::file::request*>(second), &pending);
        has_pending = true;
        return 0;
    }
    if (number == 5) {
        assert(first == 101 && third == 4096 && has_pending);
        std::memcpy(reinterpret_cast<void*>(second), &pending, sizeof(pending));
        has_pending = false;
        return 4096;
    }
    if (number == 13) return 0;
    std::abort();
}
static int open_file(const char* path, int flags = O_RDWR) {
    const long result = __xos_file_open(path, flags);
    if (result < 0) std::fprintf(stderr, "open %s => %ld\n", path, result);
    assert(result >= 0);
    return static_cast<int>(result);
}
static void checked(const char* name) { ++cases; std::printf("PASS real_service %s\n", name); }

int main(int argc, char** argv) {
    assert(argc == 2);
    identity_service_mount(argv[1]);
    xos_file_request anonymous{}; xos_file_response created{};
    anonymous.operation = 21;
    assert(__xos_file_exchange(&anonymous, &created) == 0);
    const unsigned int anonymous_handle = created.handle;
    assert(anonymous_handle != 0 && created.reserved != 0 && created.value == 0);
    anonymous.operation = 6; anonymous.handle = anonymous_handle; anonymous.length = 6;
    std::memcpy(anonymous.data, "secret", 6);
    assert(__xos_file_exchange(&anonymous, &created) == 0 && created.value == 6);
    anonymous = {}; anonymous.operation = 22; anonymous.handle = anonymous_handle;
    assert(__xos_file_exchange(&anonymous, &created) == 0);
    anonymous = {}; anonymous.operation = 7; anonymous.handle = anonymous_handle;
    assert(__xos_file_exchange(&anonymous, &created) == 0 && created.value == 0);
    anonymous = {}; anonymous.operation = 5; anonymous.handle = anonymous_handle; anonymous.length = 6;
    assert(__xos_file_exchange(&anonymous, &created) == 0 && created.length == 6);
    assert(!std::memcmp(created.data, "secret", 6));
    anonymous = {}; anonymous.operation = 6; anonymous.handle = anonymous_handle;
    anonymous.length = 1; anonymous.data[0] = 'x';
    assert(__xos_file_exchange(&anonymous, &created) == -EINVAL);
    anonymous = {}; anonymous.operation = 8; anonymous.handle = anonymous_handle;
    assert(__xos_file_exchange(&anonymous, &created) == 0);
    checked("anonymous_create_io_seal_and_close");
    const int document = static_cast<int>(__xos_file_open_anonymous());
    assert(document >= 0 && __xos_file_fcntl(document, F_GETFD, 0) == FD_CLOEXEC);
    const int alias = static_cast<int>(__xos_file_dup(document, 0, 0, 0));
    assert(alias >= 0 && alias != document);
    assert(__xos_file_write(alias, "document", 8) == 8);
    assert(__xos_file_seek(document, 0, SEEK_SET) == 0);
    assert(__xos_file_seal_anonymous(document) == 0);
    assert(__xos_file_fcntl(alias, F_GETFL, 0) == O_RDONLY);
    assert(__xos_file_write(document, "x", 1) == -EBADF);
    assert(__xos_file_write(alias, "x", 1) == -EBADF);
    assert(__xos_file_close(document) == 0);
    char document_bytes[8]{};
    assert(__xos_file_read(alias, document_bytes, sizeof(document_bytes)) == 8);
    assert(!std::memcmp(document_bytes, "document", 8));
    assert(__xos_file_close(alias) == 0);
    const int ordinary = open_file("/ordinary", O_RDWR | O_CREAT);
    assert(__xos_file_seal_anonymous(ordinary) == -EBADF);
    assert(__xos_file_fcntl(ordinary, F_GETFL, 0) == O_RDWR);
    assert(__xos_file_write(ordinary, "x", 1) == 1);
    assert(__xos_file_close(ordinary) == 0);
    checked("anonymous_fd_cloexec_seal_alias_and_failed_seal");
    unsigned int anonymous_handles[16]{};
    for (unsigned int& handle : anonymous_handles) {
        anonymous = {}; anonymous.operation = 21;
        assert(__xos_file_exchange(&anonymous, &created) == 0);
        handle = created.handle;
    }
    anonymous = {}; anonymous.operation = 21;
    assert(__xos_file_exchange(&anonymous, &created) == -EMFILE);
    for (unsigned int handle : anonymous_handles) {
        anonymous = {}; anonymous.operation = 8; anonymous.handle = handle;
        assert(__xos_file_exchange(&anonymous, &created) == 0);
    }
    checked("anonymous_quota_cleanup_then_regular_files");
    for (unsigned int length : {513U, 4097U, xos::file::max_block_bench_bytes}) {
        xos_file_request input{}; xos_file_response output{};
        input.operation = 17; input.length = length;
        const unsigned int before = block_reads;
        assert(__xos_file_exchange(&input, &output) == 0);
        assert(output.value == length && output.length == 0);
        assert(block_reads - before == (length + 4095U) / 4096U);
    }
    checked("block_bench_actual_service_and_media");
    for (unsigned int length : {0U, xos::file::max_block_bench_bytes + 1}) {
        xos_file_request input{}; xos_file_response output{};
        input.operation = 17; input.length = length;
        const unsigned int before = block_reads;
        assert(__xos_file_exchange(&input, &output) == -EINVAL && block_reads == before);
    }
    checked("block_bench_invalid_requests_preserve_session");
    int first = open_file("/g3", O_CREAT | O_EXCL | O_RDWR);
    assert(__xos_file_write(first, "abcdef", 6) == 6);
    int second = open_file("/g3", O_RDONLY);
    struct stat a{}, b{};
    assert(__xos_file_stat(first, nullptr, &a) == 0 && __xos_file_stat(second, nullptr, &b) == 0);
    assert(a.st_ino == b.st_ino && a.st_size == 6 && a.st_mode == (S_IFREG | 0644));
    char data[32]{};
    assert(__xos_file_read(second, data, 2) == 2 && !std::memcmp(data, "ab", 2));
    assert(__xos_file_seek(first, 0, SEEK_CUR) == 6);
    checked("independent_open_metadata_after_block_bench");

    int duplicate = static_cast<int>(__xos_file_dup(second, 0, 0, 0));
    assert(duplicate >= 0 && __xos_file_read(duplicate, data, 2) == 2 && !std::memcmp(data, "cd", 2));
    assert(__xos_file_seek(second, 0, SEEK_CUR) == 4);
    assert(__xos_file_close(duplicate) == 0);
    checked("duplicate_shared_offset");

    assert(__xos_file_seek(first, 10, SEEK_SET) == 10 && __xos_file_write(first, "x", 1) == 1);
    assert(__xos_file_seek(second, 6, SEEK_SET) == 6 && __xos_file_read(second, data, 5) == 5);
    assert(!std::memcmp(data, "\0\0\0\0x", 5));
    assert(__xos_file_truncate(first, 3) == 0);
    assert(__xos_file_stat(second, nullptr, &b) == 0 && b.st_size == 3);
    checked("sparse_zero_fill_and_truncate");

    assert(__xos_file_path_op("/g3", 13) == 0 && __xos_file_stat(second, nullptr, &b) == 0);
    assert(b.st_nlink == 0 && b.st_ino == a.st_ino);
    int replacement = open_file("/g3", O_CREAT | O_RDWR);
    assert(__xos_file_write(replacement, "new", 3) == 3 && __xos_file_stat(replacement, nullptr, &b) == 0);
    assert(b.st_ino != a.st_ino);
    assert(__xos_file_seek(second, 0, SEEK_SET) == 0 && __xos_file_read(second, data, 3) == 3);
    assert(!std::memcmp(data, "abc", 3));
    assert(__xos_file_close(first) == 0 && __xos_file_close(second) == 0 && __xos_file_close(replacement) == 0);
    checked("unlink_recreate_retained_identity");

    first = open_file("/g3", O_WRONLY | O_APPEND);
    second = open_file("/g3", O_RDWR | O_APPEND);
    assert(__xos_file_write(first, "1", 1) == 1 && __xos_file_write(second, "2", 1) == 1);
    assert(__xos_file_seek(second, 0, SEEK_SET) == 0 && __xos_file_read(second, data, 5) == 5);
    assert(!std::memcmp(data, "new12", 5));
    assert(__xos_file_close(first) == 0 && __xos_file_close(second) == 0);
    checked("independent_append_current_eof");

    first = open_file("/g3", O_RDWR);
    write_fault_after = 2;
    assert(__xos_file_write(first, "abcdef", 6) == 2);
    assert(__xos_file_seek(first, 0, SEEK_SET) == 0);
    read_fault_after = 1;
    assert(__xos_file_read(first, data, 4) == 1);
    assert(__xos_file_seek(first, 0, SEEK_SET) == 0);
    write_calls = 0; write_fail_nth = 1;
    assert(__xos_file_write(first, "z", 1) == -ENOSPC);
    assert(__xos_file_close(first) == 0);
    checked("partial_io_and_no_space");

    assert(__xos_file_path_op("/g3dir", 15) == 0);
    first = open_file("/g3dir/", O_RDONLY);
    assert(__xos_file_stat(first, nullptr, &a) == 0 && S_ISDIR(a.st_mode));
    assert(__xos_file_read(first, data, 1) == -EISDIR);
    assert(__xos_file_close(first) == 0);
    assert(__xos_file_open("/g3/", O_RDONLY) == -ENOTDIR);
    assert(__xos_file_open("/missing/../g3", O_RDONLY) == -ENOENT);
    assert(__xos_file_open("/g3/../g3", O_RDONLY) == -ENOTDIR);
    checked("directory_and_component_errors");

    first = open_file("/dev/null", O_RDWR);
    assert(__xos_file_write(first, "discard", 7) == 7 && __xos_file_read(first, data, 8) == 0);
    assert(__xos_file_stat(first, nullptr, &a) == 0 && a.st_ino == 65535);
    assert(__xos_file_close(first) == 0);
    checked("reserved_device_identity");

    int slots[16];
    for (int i = 0; i < 16; ++i) slots[i] = open_file("/g3", O_RDONLY);
    assert(__xos_file_open("/g3", O_RDONLY) == -EMFILE);
    for (int slot : slots) assert(__xos_file_close(slot) == 0);
    checked("service_quota_and_reuse");
    identity_service_finished();
    checked("all_remote_descriptions_reclaimed");
    std::printf("PASS %u real glibc FD/files/FatFs integration groups\n", cases);
}
