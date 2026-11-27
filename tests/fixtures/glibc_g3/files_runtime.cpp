// SPDX-License-Identifier: Apache-2.0
// Exercise the production C FD/session state machine; replace only kernel traps.
#include "xos_file_runtime.h"
#include <xos/file_abi.hpp>
#include <xos/file_client.hpp>
#include <xos/spawn.hpp>
#include <xos/thread_abi.hpp>
#include <atomic>
#include <cassert>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <linux/futex.h>
#include <mutex>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <thread>
#include <unistd.h>
#include <vector>

static_assert(sizeof(xos_file_request) == sizeof(xos::file::request));
static_assert(sizeof(xos_file_response) == sizeof(xos::file::response));
static_assert(offsetof(xos_file_request, data) == offsetof(xos::file::request, data));
static_assert(offsetof(xos_file_response, data) == offsetof(xos::file::response, data));
static_assert(offsetof(xos_file_response, value) == offsetof(xos::file::response, value));
static_assert(static_cast<unsigned int>(xos_file_stat_check_exec) == xos::file::stat_check_exec);
static_assert(static_cast<unsigned int>(xos_file_stat_exec_checked) == xos::file::stat_exec_checked);
static_assert(sizeof(xos_file_startup) == sizeof(xos::startup_info));
static_assert(sizeof(xos_file_startup_extension) == sizeof(xos::startup_extension));
static_assert(sizeof(xos_file_startup_exec) == sizeof(xos::startup_exec_extension));
static_assert(sizeof(xos_file_startup_descriptor) == sizeof(xos::startup_descriptor));

extern "C" { const void *__xos_startup = nullptr; }
extern "C" long xos_test_writev(int, const struct iovec*, int);
alignas(16) static unsigned char startup_area[4096];
static std::mutex mock_lock;
static xos_file_response pending;
static bool has_pending;
static unsigned int last_sequence, sends, opens, closes, pipe_closes;
static unsigned int reply_waits, reply_sleeps;
static xos_u64 reply_deadline;
static unsigned int last_stat_flags;
static long now_ns = 100;
static const char* failure;
static bool failure_armed;
static std::atomic<bool> pipe_waiting, pipe_release;
static std::atomic<bool> runtime_waiting;
static bool vector_write;
struct file_description { bool active; unsigned int position, flags; };
static file_description files[17];
static unsigned char content[32768];
static unsigned int content_size;
static bool exists = true;

extern "C" int __xos_file_test_startup_range(xos_u64 address, xos_u64 length) {
    const auto begin = reinterpret_cast<xos_u64>(startup_area);
    return address >= begin && address <= begin + sizeof(startup_area) &&
        length <= begin + sizeof(startup_area) - address;
}
extern "C" xos_i64 __xos_wait_word(xos_u32* address, xos_u32 expected, xos_u64 deadline) {
    runtime_waiting = true;
    if (deadline != ~xos_u64{0}) {
        assert(failure && !std::strcmp(failure, "bounded_lock"));
        now_ns = static_cast<long>(deadline);
        return xos::thread_error_timeout;
    }
    const long result = syscall(SYS_futex, address, FUTEX_WAIT_PRIVATE, expected, nullptr, nullptr, 0);
    return result == 0 ? 0 : errno == EAGAIN ? -14 : -11;
}
extern "C" xos_i64 __xos_wake_word(xos_u32* address, xos_u32 count) {
    return syscall(SYS_futex, address, FUTEX_WAKE_PRIVATE, count, nullptr, nullptr, 0);
}

static void metadata() {
    pending.value = content_size;
    pending.reserved = 7;
    pending.length = 24;
    std::memcpy(pending.data, "FMET\1\0\30\0", 8);
    const xos_u64 seconds = 1700000000;
    const xos_u32 mode = S_IFREG | 0644;
    std::memcpy(pending.data + 8, &seconds, 8);
    std::memcpy(pending.data + 20, &mode, 4);
}

static void process_request(const xos_file_request& input) {
    assert(!has_pending);
    assert(input.magic == xos::file::request_magic && input.version == xos::file::abi_version);
    assert(input.request_id == last_sequence + 1 && input.reserved == 0);
    last_sequence = input.request_id;
    ++sends;
    pending = {};
    pending.magic = xos::file::response_magic;
    pending.version = xos::file::abi_version;
    pending.request_id = input.request_id;
    const auto operation = static_cast<xos::file::op>(input.operation);
    if (operation == xos::file::op::list) {
        const bool identity = (input.flags & (1U << 12)) != 0;
        pending.flags = identity ? 1U << 12 : 0;
        const unsigned int header = identity ? 13U : 7U;
        unsigned int at = 0;
        for (unsigned int index = 0; index < 2; ++index) {
            pending.data[at] = static_cast<unsigned char>(index + 1);
            pending.data[at + 2] = 1;
            if (identity) {
                pending.data[at + 7] = static_cast<unsigned char>(7 + index);
                pending.data[at + 9] = static_cast<unsigned char>(index + 1);
            }
            if (index == 0) pending.data[at + header] = '.';
            else { pending.data[at + header] = 0xc3; pending.data[at + header + 1] = 0xa9; }
            at += header + index + 1;
        }
        pending.length = at;
    } else if (operation == xos::file::op::anonymous) {
        unsigned int handle = 1;
        while (handle <= 16 && files[handle].active) ++handle;
        if (handle == 17) pending.status_code = -3;
        else {
            files[handle] = {true, 0, xos::file::read_write};
            content_size = 0;
            pending.handle = handle;
            pending.reserved = 7;
        }
    } else if (operation == xos::file::op::open) {
        ++opens;
        assert(input.name_length > 0 && input.name_length < 256 && input.name[input.name_length] == 0);
        if (!std::strcmp(input.name, "/missing") || (!exists && !(input.flags & xos::file::open_create)))
            pending.status_code = -1;
        else if (input.flags & xos::file::open_directory) pending.status_code = -10;
        else {
            unsigned int handle = 1;
            while (handle <= 16 && files[handle].active) ++handle;
            if (handle == 17) pending.status_code = -3;
            else if (exists && (input.flags & xos::file::open_create) && (input.flags & xos::file::open_exclusive))
                pending.status_code = -9;
            else {
                exists = true;
                if (input.flags & xos::file::open_truncate) content_size = 0;
                files[handle] = {true, 0, input.flags};
                pending.handle = handle;
                pending.reserved = 7;
                pending.value = content_size;
            }
        }
    } else if (operation == xos::file::op::stat) {
        assert(input.flags == 0 || input.flags == xos::file::stat_check_exec);
        last_stat_flags = input.flags;
        if (!exists) pending.status_code = -1;
        else metadata();
    } else if (operation == xos::file::op::remove) {
        if (!exists) pending.status_code = -1;
        else exists = false;
    } else if (operation == xos::file::op::sync) {
    } else if (operation == xos::file::op::cwd_set) {
        assert(input.offset <= 78 && !std::strcmp(input.name, "/updated"));
    } else if (operation == xos::file::op::block_bench) {
        pending.value = input.length;
    } else {
        assert(input.handle > 0 && input.handle <= 16);
        auto& file = files[input.handle];
        if (!file.active) pending.status_code = -6;
        else if (operation == xos::file::op::close) { ++closes; file.active = false; }
        else if (operation == xos::file::op::write) {
            assert(input.length <= xos::file::request_data_size);
            if (file.flags & xos::file::open_append) file.position = content_size;
            assert(file.position + input.length <= sizeof(content));
            std::memcpy(content + file.position, input.data, input.length);
            file.position += input.length;
            if (file.position > content_size) content_size = file.position;
            pending.value = input.length;
        } else if (operation == xos::file::op::read) {
            const unsigned int wanted = input.length > xos::file::response_data_size
                ? xos::file::response_data_size : input.length;
            const unsigned int remaining = file.position < content_size ? content_size - file.position : 0;
            pending.length = wanted < remaining ? wanted : remaining;
            std::memcpy(pending.data, content + file.position, pending.length);
            file.position += pending.length;
            pending.value = pending.length;
        } else if (operation == xos::file::op::seek) {
            const long base = input.flags == 0 ? 0 : input.flags == 1 ? file.position : content_size;
            const long position = base + static_cast<long>(input.offset);
            if (position < 0 || position > 32768) pending.status_code = -2;
            else { file.position = static_cast<unsigned int>(position); pending.value = file.position; }
        } else if (operation == xos::file::op::fstat) metadata();
        else if (operation == xos::file::op::truncate) content_size = static_cast<unsigned int>(input.offset);
        else std::abort();
    }
    has_pending = true;
}

extern "C" long __xos_file_test_trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third) {
    if (number == 54) {
        assert(first == 70000 && second == 3);
        pipe_waiting = true;
        while (!pipe_release.load()) std::this_thread::yield();
        return 0;
    }
    std::lock_guard<std::mutex> guard(mock_lock);
    switch (number) {
    case 6: return 77;
    case 22: {
        auto* handles = reinterpret_cast<xos_u32*>(first);
        handles[0] = 100; handles[1] = 101;
        if (failure && !std::strcmp(failure, "no_session")) handles[0] = 0;
        return 0;
    }
    case 46:
        if (failure_armed && !std::strcmp(failure, "clock_failure")) return -5;
        if (failure_armed && !std::strcmp(failure, "late_reply")) now_ns += 5000000001L;
        return now_ns++;
    case 47:
        ++reply_sleeps;
        now_ns = static_cast<long>(first);
        return 0;
    case xos::sys_ipc_wait:
        assert(failure != nullptr && failure_armed);
        assert(first == 101 && second == static_cast<xos_u64>(xos::ipc_wait_mode::file_reply_until));
        assert(third > static_cast<xos_u64>(now_ns));
        if (reply_waits++ == 0) reply_deadline = third;
        else assert(third == reply_deadline);
        if (!std::strcmp(failure, "wait_timeout")) return xos::thread_error_timeout;
        if (!std::strcmp(failure, "wait_death")) return xos::pipe_error_broken;
        if (!std::strcmp(failure, "wait_interrupted")) return -EINTR;
        if (!std::strcmp(failure, "wait_at_deadline")) now_ns = static_cast<long>(third);
        return !std::strcmp(failure, "timeout") || !std::strcmp(failure, "wait_legacy") ? -2 : 0;
    case 4:
        assert(first == 100 && third == sizeof(xos_file_request));
        if (failure_armed && !std::strcmp(failure, "send_failure")) return -1;
        process_request(*reinterpret_cast<const xos_file_request*>(second));
        return 0;
    case 5:
        assert(first == 101 && third == sizeof(pending));
        if (failure_armed && !std::strcmp(failure, "timeout")) return -3;
        if (failure_armed && !std::strcmp(failure, "service_death")) return -1;
        if (failure_armed && !std::strncmp(failure, "wait_", 5) &&
            reply_waits < (!std::strcmp(failure, "wait_spurious") ? 2U : 1U)) return -3;
        if (!has_pending) return -3;
        if (failure_armed) {
            if (!std::strcmp(failure, "wrong_sequence")) ++pending.request_id;
            if (!std::strcmp(failure, "wait_duplicate")) --pending.request_id;
            if (!std::strcmp(failure, "bad_magic")) pending.magic = 0;
            if (!std::strcmp(failure, "bad_version")) pending.version = 3;
            if (!std::strcmp(failure, "overread")) pending.length = 3799;
            if (!std::strcmp(failure, "overwrite")) pending.value = 3801;
            if (!std::strcmp(failure, "unknown_status")) pending.status_code = 1;
            if (!std::strcmp(failure, "metadata")) pending.data[0] = 0;
            if (!std::strcmp(failure, "block_bad_value")) ++pending.value;
            if (!std::strcmp(failure, "block_bad_payload")) pending.length = 1;
            if (!std::strcmp(failure, "anonymous_bad_handle")) pending.handle = 0;
            if (!std::strcmp(failure, "anonymous_bad_inode")) pending.reserved = 0;
            if (!std::strcmp(failure, "anonymous_bad_flags")) pending.flags = 1;
            if (!std::strcmp(failure, "anonymous_bad_size")) pending.value = 1;
            if (!std::strcmp(failure, "anonymous_bad_payload")) pending.length = 1;
            if (!std::strcmp(failure, "directory_bad_cursor")) pending.data[23] = 1;
            if (!std::strcmp(failure, "directory_bad_identity")) pending.data[7] = 0;
            if (!std::strcmp(failure, "directory_bad_utf8")) pending.data[27] = 0xc0;
            if (!std::strcmp(failure, "directory_truncated")) --pending.length;
            if (!std::strcmp(failure, "directory_empty_progress")) {
                pending.length = 0; pending.value = 2;
            }
        }
        std::memcpy(reinterpret_cast<void*>(second), &pending, sizeof(pending));
        has_pending = false;
        return failure_armed && !std::strcmp(failure, "short_reply") ? 4095 : 4096;
    case 34: return first == 0 && second <= 2 ? 1 : -1;
    case 11:
        assert((first & 0x7fffffffffffffffULL) <= 2 && third <= 256);
        return static_cast<long>(third);
    case 12: return 0;
    case 13: assert(first <= 2); return 0;
    case 33: assert(first == 70000); ++pipe_closes; return 0;
    case 32:
        assert(first == (70000ULL | (1ULL << 63)));
        if (vector_write) {
            assert(third == 4096);
            const auto* bytes = reinterpret_cast<const unsigned char*>(second);
            for (int i = 0; i < 4096; ++i) assert(bytes[i] == (i < 2000 ? 'a' : 'b'));
            return 4096;
        }
        assert(third == 3);
        return pipe_release.load() ? 3 : -3;
    default: std::abort();
    }
}

namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    return __xos_file_test_trap(number, first, second, third);
}
}

static void setup_startup(unsigned int version) {
    __xos_startup = startup_area;
    auto* startup = reinterpret_cast<xos_file_startup*>(startup_area);
    *startup = {xos::startup_magic, version, 48, 0, 3, 0, {0, 1, 2}, version == 1 ? 0U : 64U};
    if (version > 1) {
        auto* extension = reinterpret_cast<xos_file_startup_extension*>(startup_area + 64);
        extension->magic = xos::startup_extension_magic;
        auto* exec = reinterpret_cast<xos_file_startup_exec*>(startup_area + 152);
        exec->magic = xos::startup_exec_magic;
        exec->descriptors = reinterpret_cast<xos_u64>(startup_area + 256);
    }
}

static void basic() {
    errno = 123;
    assert(__xos_file_read(31, nullptr, 0) == -EBADF);
    assert(__xos_file_write(0, nullptr, 0) == -EBADF);
    assert(__xos_file_open("/missing", O_RDONLY) == -ENOENT);
    const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR | O_TRUNC | O_CLOEXEC));
    assert(fd == 3 && errno == 123);
    assert(__xos_file_fcntl(fd, F_GETFD, 0) == FD_CLOEXEC);
    assert(__xos_file_write(fd, "abcdef", 6) == 6);
    const int duplicate = static_cast<int>(__xos_file_dup(fd, 0, 0, 0));
    assert(duplicate == 4 && __xos_file_fcntl(duplicate, F_GETFD, 0) == 0);
    assert(__xos_file_seek(duplicate, 0, SEEK_SET) == 0);
    char buffer[8]{};
    assert(__xos_file_read(fd, buffer, 2) == 2 && !std::memcmp(buffer, "ab", 2));
    assert(__xos_file_read(duplicate, buffer, 2) == 2 && !std::memcmp(buffer, "cd", 2));
    assert(__xos_file_close(fd) == 0 && closes == 0);
    assert(__xos_file_read(duplicate, buffer, 4) == 2 && !std::memcmp(buffer, "ef", 2));
    assert(__xos_file_read(duplicate, buffer, 4) == 0);
    struct stat info{};
    assert(__xos_file_stat(duplicate, nullptr, &info) == 0);
    assert(info.st_size == 6 && info.st_ino == 7 && info.st_mode == (S_IFREG | 0644));
    assert(info.st_mtime == 1700000000 && info.st_mtim.tv_nsec == 0 && info.st_blocks == 1);
    assert(__xos_file_sync(duplicate) == 0);
    assert(__xos_file_close(duplicate) == 0 && closes == 1);
    assert(__xos_file_close(duplicate) == -EBADF);
    assert(__xos_file_close(0) == 0 && __xos_file_open("/fixture", O_RDONLY) == 0);
    assert(__xos_file_write(0, "x", 1) == -EBADF);
    assert(__xos_file_seek(1, 0, SEEK_SET) == -ESPIPE);
    assert(__xos_file_isatty(1) == 1 && __xos_file_isatty(0) == -ENOTTY);
}

static void bounds() {
    char path[257]; std::memset(path, 'a', sizeof(path)); path[256] = 0;
    assert(__xos_file_open(nullptr, O_RDONLY) == -EFAULT);
    assert(__xos_file_open("", O_RDONLY) == -ENOENT);
    assert(__xos_file_open(path, O_RDONLY) == -ENAMETOOLONG);
    assert(__xos_file_open("/\n", O_RDONLY) == -EINVAL);
    assert(__xos_file_open("/fixture", O_ACCMODE) == -EINVAL);
    assert(__xos_file_open("/fixture", INT_MIN) == -EINVAL);
    assert(sends == 0);
    int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
    assert(__xos_file_write(fd, nullptr, 1) == -EFAULT);
    assert(__xos_file_read(fd, nullptr, 0) == 0);
    assert(__xos_file_dup(fd, 32, 1, 0) == -EBADF);
    assert(__xos_file_dup(31, 31, 1, 0) == -EBADF);
    assert(__xos_file_dup(fd, fd, 1, 0) == fd);
    assert(__xos_file_fcntl(fd, F_SETFD, 2) == -EINVAL);
    assert(__xos_file_fcntl(fd, F_SETFL, O_APPEND) == -ENOTSUP);
    unsigned char bytes[4096]{};
    assert(__xos_file_write(fd, bytes, sizeof(bytes)) == 3800);
    assert(__xos_file_seek(fd, 0, 0) == 0);
    assert(__xos_file_read(fd, bytes, sizeof(bytes)) == 3798);
    assert(__xos_file_truncate(fd, -1) == -EINVAL);
    assert(__xos_file_truncate(fd, 0x100000000L) == -EFBIG);
    for (int i = 4; i < 32; ++i) assert(__xos_file_dup(fd, 0, 0, 0) == i);
    const unsigned int before = sends;
    assert(__xos_file_open("/fixture", O_TRUNC | O_RDWR) == -EMFILE);
    assert(sends == before && content_size == 3800);
    for (int i = 3; i < 32; ++i) assert(__xos_file_close(i) == 0);
    assert(closes == 1);
}

static void concurrent() {
    const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR | O_TRUNC));
    std::vector<std::thread> workers;
    for (int t = 0; t < 6; ++t) workers.emplace_back([fd] {
        for (int i = 0; i < 1000; ++i) assert(__xos_file_write(fd, "x", 1) == 1);
    });
    for (auto& worker : workers) worker.join();
    assert(content_size == 6000 && sends == 6001 && last_sequence == sends);
    assert(__xos_file_close(fd) == 0 && closes == 1);
}

static void inheritance(const char* scenario) {
    setup_startup(3);
    auto* exec = reinterpret_cast<xos_file_startup_exec*>(startup_area + 152);
    const auto offset = !std::strcmp(scenario, "inheritance_word_aligned") ? 260 : 256;
    auto* entries = reinterpret_cast<xos_file_startup_descriptor*>(startup_area + offset);
    exec->descriptors = reinterpret_cast<xos_u64>(entries);
    exec->count = 3;
    entries[0] = {5, 4, 2, 1, O_RDWR, 0};
    entries[1] = {6, 4, 2, 1, O_RDWR, 0};
    entries[2] = {~0U, 8, 2, 2, O_RDWR, 0};
    files[1] = {true, 0, 3}; files[2] = {true, 0, 3};
    if (!std::strcmp(scenario, "invalid_inheritance")) {
        entries[1].fd = 5;
        assert(__xos_file_write(5, "x", 1) == -EINVAL && sends == 0);
        return;
    }
    if (!std::strcmp(scenario, "duplicate_cleanup")) {
        entries[0].fd = ~0U; entries[1].fd = ~0U;
        assert(__xos_file_write(5, "x", 1) == -EINVAL && sends == 0);
        return;
    }
    assert(__xos_file_write(5, "x", 1) == 1 && closes == 1 && opens == 0);
    assert(__xos_file_seek(6, 0, SEEK_CUR) == 1);
    assert(__xos_file_fcntl(6, F_GETFD, 0) == 0);
    assert(__xos_file_close(5) == 0 && closes == 1);
    assert(__xos_file_close(6) == 0 && closes == 2);
}

static void inheritance_v2(const char* scenario) {
    setup_startup(2);
    auto* extension = reinterpret_cast<xos_file_startup_extension*>(startup_area + 64);
    extension->flags = (1U << 9) | (1U << 2);
    extension->file_handles[1] = 1;
    extension->open_flags[1] = O_RDWR;
    files[1] = {true, 2, 3};
    std::memcpy(content, "abcdef", 6);
    content_size = 6;
    if (!std::strcmp(scenario, "duplicate_v2_handle")) {
        extension->flags |= 1U << 8;
        extension->file_handles[0] = 1;
        extension->open_flags[0] = O_RDWR;
        assert(__xos_file_read(1, content, 1) == -EINVAL && sends == 0);
        return;
    }
    if (!std::strcmp(scenario, "path_v2_redirection")) {
        extension->flags &= ~(1U << 9);
        extension->file_handles[1] = 0;
        extension->open_paths[1] = reinterpret_cast<xos_u64>(startup_area + 256);
        assert(__xos_file_read(1, content, 1) == -ENOTSUP && sends == 0);
        return;
    }
    char bytes[2];
    assert(__xos_file_read(1, bytes, 2) == 2 && !std::memcmp(bytes, "cd", 2));
    assert(opens == 0 && __xos_file_seek(1, 0, SEEK_CUR) == 4);
    assert(__xos_file_read(2, bytes, 1) == -EBADF);
    assert(__xos_file_close(1) == 0 && closes == 1);
}

static void spawn_cwd_serialization() {
    xos_spawn_stdio snapshot{};
    assert(__xos_file_spawn_begin(&snapshot) == 0);
    xos::file::client loader;
    assert(loader.set_cwd("/updated", 78) == 0 && sends == 1);
    __xos_file_spawn_end(&snapshot);

    enum { chdir_path, session_self, native_self };
    for (const auto entry : {chdir_path, session_self, native_self}) {
        assert(__xos_file_spawn_begin(&snapshot) == 0);
        const unsigned int previous_sends = sends;
        runtime_waiting = false;
        std::atomic<bool> completed{false};
        std::thread changer([&] {
            if (entry == chdir_path) {
                assert(__xos_file_chdir("/updated") == 0);
            } else if (entry == session_self) {
                xos_file_request input{};
                xos_file_response output{};
                input.operation = static_cast<xos_file_u16>(xos::file::op::cwd_set);
                assert(__xos_file_request_path(&input, "/updated") == 0);
                assert(__xos_file_exchange(&input, &output) == 0);
            } else {
                xos::file::client native;
                assert(native.set_cwd("/updated", 77) == 0);
            }
            completed = true;
        });
        while (!runtime_waiting.load() && !completed.load()) std::this_thread::yield();
        assert(runtime_waiting.load() && !completed.load() && sends == previous_sends);
        __xos_file_spawn_end(&snapshot);
        changer.join();
        assert(completed.load() && sends == previous_sends + 1);
    }
}

static void pipe_lease() {
    setup_startup(3);
    auto* exec = reinterpret_cast<xos_file_startup_exec*>(startup_area + 152);
    auto* entries = reinterpret_cast<xos_file_startup_descriptor*>(startup_area + 256);
    exec->count = 1;
    entries[0] = {3, 3, 4, 70000, O_WRONLY, 0};
    std::thread writer([] { assert(__xos_file_write(3, "abc", 3) == 3); });
    while (!pipe_waiting.load()) std::this_thread::yield();
    assert(__xos_file_close(3) == 0 && pipe_closes == 0);
    assert(__xos_file_open("/fixture", O_RDWR) == 0);
    pipe_release = true;
    writer.join();
    assert(pipe_closes == 1);
}

static void pipe_writev() {
    setup_startup(3);
    auto* exec = reinterpret_cast<xos_file_startup_exec*>(startup_area + 152);
    auto* entries = reinterpret_cast<xos_file_startup_descriptor*>(startup_area + 256);
    exec->count = 1;
    entries[0] = {3, 3, 4, 70000, O_WRONLY, 0};
    unsigned char a[2000], b[2096];
    std::memset(a, 'a', sizeof(a)); std::memset(b, 'b', sizeof(b));
    const struct iovec vectors[2] = {{a, sizeof(a)}, {b, sizeof(b)}};
    vector_write = true;
    assert(xos_test_writev(3, vectors, 2) == 4096);
    assert(__xos_file_close(3) == 0 && pipe_closes == 1);
    assert(xos_test_writev(3, nullptr, 0) == -1 && errno == EBADF);
}

static void public_lease() {
    const int old_fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
    assert(old_fd == 3 && __xos_file_write(old_fd, "abcdef", 6) == 6);
    assert(__xos_file_seek(old_fd, 1, SEEK_SET) == 1);
    xos_file_lease lease{}, invalid{};
    assert(__xos_file_lease_acquire(1, 0, &invalid) == -EBADF && invalid.object == -1);
    assert(__xos_file_lease_acquire(old_fd, 0, &lease) == 0);
    assert(__xos_file_close(old_fd) == 0 && closes == 0);
    const int replacement = static_cast<int>(__xos_file_open("/fixture", O_RDONLY));
    assert(replacement == old_fd);
    xos_file_request input{}; xos_file_response output{};
    input.operation = 5; input.handle = lease.handle; input.length = 2;
    assert(__xos_file_exchange(&input, &output) == 0);
    assert(output.length == 2 && !std::memcmp(output.data, "bc", 2));
    char byte = 0;
    assert(__xos_file_read(replacement, &byte, 1) == 1 && byte == 'a');
    assert(__xos_file_lease_release(&lease) == 0 && closes == 1 && lease.object == -1);
    assert(__xos_file_lease_release(&lease) == -EINVAL && closes == 1);
    assert(__xos_file_close(replacement) == 0 && closes == 2);
    input = {}; input.operation = 4; input.flags = 1;
    assert(__xos_file_request_path(&input, "/missing") == 0);
    std::memset(&output, 0xff, sizeof(output));
    assert(xos_file_session_exchange(&input, &output) == -1);
    const xos_file_response empty{};
    assert(!std::memcmp(&output, &empty, sizeof(output)));
}

static void directory_exchange(const char* scenario) {
    const bool legacy = !std::strcmp(scenario, "directory_legacy");
    const bool success = legacy || !std::strcmp(scenario, "directory_identity")
        || !std::strcmp(scenario, "directory_default_limit");
    xos_file_request input{}; xos_file_response output{};
    input.operation = 2; input.flags = legacy ? 1U << 8 : (1U << 8) | (1U << 12);
    input.length = 2;
    if (!std::strcmp(scenario, "directory_bad_count")) input.length = 1;
    if (!std::strcmp(scenario, "directory_default_limit")) input.length = 0;
    assert(__xos_file_request_path(&input, "/") == 0);
    if (!success) { failure = scenario; failure_armed = true; }
    assert(__xos_file_exchange(&input, &output) == (success ? 0 : -EIO));
    if (success) {
        assert(output.flags == (legacy ? 0U : 1U << 12));
        assert(output.length == (legacy ? 17U : 29U) && output.value == 0);
    } else {
        const unsigned int before = sends;
        const xos_file_response empty{};
        assert(!std::memcmp(&output, &empty, sizeof(output)));
        failure_armed = false;
        assert(__xos_file_exchange(&input, &output) == -EIO && sends == before);
    }
}

static void native_read_capacity() {
    const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
    unsigned char bytes[3800];
    for (unsigned int i = 0; i < sizeof(bytes); ++i) bytes[i] = static_cast<unsigned char>(i * 17U);
    assert(__xos_file_write(fd, bytes, sizeof(bytes)) == sizeof(bytes));
    assert(__xos_file_seek(fd, 0, SEEK_SET) == 0);
    xos_file_lease lease{};
    assert(__xos_file_lease_acquire(fd, 0, &lease) == 0);
    xos::file::client native;
    assert(native.init());
    unsigned char output[3800]{};
    assert(native.read(lease.handle, output, sizeof(output)) == 3798);
    assert(!std::memcmp(output, bytes, 3798));
    unsigned char tail[2]{};
    assert(__xos_file_read(fd, tail, sizeof(tail)) == 2);
    assert(!std::memcmp(tail, bytes + 3798, 2));
    assert(__xos_file_lease_release(&lease) == 0 && __xos_file_close(fd) == 0);
}

static void block_bench(const char* scenario) {
    const bool success = !std::strcmp(scenario, "block_valid");
    xos_file_request input{};
    input.operation = 17;
    input.length = 513;
    if (!std::strcmp(scenario, "block_zero_success")) input.length = 0;
    if (!std::strcmp(scenario, "block_large_success"))
        input.length = xos::file::max_block_bench_bytes + 1;
    xos_file_response output{};
    failure = scenario; failure_armed = !success;
    assert(__xos_file_exchange(&input, &output) == (success ? 0 : -EIO));
    if (success) {
        assert(output.value == input.length && output.length == 0);
        xos::file::client native;
        assert(native.init() && native.block_bench(xos::file::max_block_bench_bytes)
               == xos::file::max_block_bench_bytes);
        const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
        assert(fd == 3 && __xos_file_write(fd, "ok", 2) == 2 && __xos_file_close(fd) == 0);
    } else {
        const unsigned int before = sends;
        const xos_file_response empty{};
        assert(!std::memcmp(&output, &empty, sizeof(output)));
        failure_armed = false;
        input.operation = 1;
        assert(__xos_file_exchange(&input, &output) == -EIO && sends == before);
    }
}

static void anonymous_exchange(const char* scenario) {
    const bool success = !std::strcmp(scenario, "anonymous_valid");
    xos_file_request input{}; xos_file_response output{};
    input.operation = 21;
    failure = scenario; failure_armed = !success;
    assert(__xos_file_exchange(&input, &output) == (success ? 0 : -EIO));
    if (success) {
        assert(output.handle != 0 && output.reserved == 7 && output.value == 0);
        xos::file::client native;
        assert(native.init() && native.close(output.handle) == 0);
        xos::u32 handle = 0;
        assert(native.anonymous(handle) == 0 && handle != 0);
        assert(native.write(handle, "ok", 2) == 2);
        assert(native.seek(handle, 0) == 0);
        char bytes[2]{};
        assert(native.read(handle, bytes, 2) == 2 && !std::memcmp(bytes, "ok", 2));
        assert(native.close(handle) == 0);
        const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
        assert(fd == 3 && __xos_file_close(fd) == 0);
    } else {
        const unsigned int before = sends;
        const xos_file_response empty{};
        assert(!std::memcmp(&output, &empty, sizeof(output)));
        failure_armed = false;
        assert(__xos_file_exchange(&input, &output) == -EIO && sends == before);
    }
}

static void error_case(const char* scenario) {
    failure = scenario;
    if (!std::strcmp(scenario, "no_session")) {
        assert(__xos_file_open("/fixture", O_RDWR) == -EIO && sends == 0);
        return;
    }
    const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
    assert(fd == 3);
    failure_armed = true;
    long result;
    if (!std::strcmp(scenario, "metadata")) { struct stat st{}; result = __xos_file_stat(fd, nullptr, &st); }
    else result = __xos_file_write(fd, "x", 1);
    const bool timeout = !std::strcmp(scenario, "timeout") || !std::strcmp(scenario, "late_reply") ||
        !std::strcmp(scenario, "wait_timeout") || !std::strcmp(scenario, "wait_at_deadline");
    assert(result == (timeout ? -ETIMEDOUT : -EIO));
    const unsigned int sent = sends;
    failure_armed = false;
    assert(__xos_file_write(fd, "y", 1) == -EIO && sends == sent);
    assert(__xos_file_close(fd) == -EIO && sends == sent);
    assert(__xos_file_close(fd) == -EBADF);
    assert(content_size <= 1);
    if (!std::strncmp(scenario, "wait_", 5)) assert(reply_waits == 1 && reply_sleeps == 0);
}

static void reply_ready(const char* scenario, unsigned int waits, unsigned int sleeps) {
    failure = scenario;
    const long fd = __xos_file_open("/fixture", O_RDWR);
    assert(fd == 3);
    failure_armed = true;
    assert(__xos_file_write(3, "x", 1) == 1);
    assert(reply_waits == waits && reply_sleeps == sleeps && sends == 2);
    failure_armed = false;
    assert(__xos_file_close(3) == 0);
}

static void access_legacy_stat() {
    // The old service understands stat but omits the executable-probe bit.
    assert(__xos_file_access("/fixture", X_OK) == -ENOTSUP);
    assert(last_stat_flags == xos::file::stat_check_exec);
    assert(__xos_file_access("/fixture", R_OK | W_OK) == 0);
    assert(last_stat_flags == 0 && sends == 2 && opens == 0 && closes == 0);
}

static void native_deadline(const char* scenario) {
    xos::file::client native;
    assert(native.init());
    assert(!native.set_deadline(1ULL << 63));
    if (!std::strcmp(scenario, "native_deadline_expired")) {
        assert(native.set_deadline(1));
        xos::u32 bytes = 0, version = 0;
        assert(native.stat("/fixture", bytes, version) == xos::file::transport_timeout && sends == 0);
        assert(native.set_deadline(1000000));
        assert(native.stat("/fixture", bytes, version) == 0 && sends == 1);
    } else if (!std::strcmp(scenario, "native_deadline_lock")) {
        xos_spawn_stdio snapshot{};
        assert(__xos_file_spawn_begin(&snapshot) == 0);
        failure = "bounded_lock";
        assert(native.set_deadline(1000000));
        assert(native.set_cwd("/updated", 77) == xos::file::transport_timeout);
        assert(runtime_waiting && sends == 0);
        __xos_file_spawn_end(&snapshot);
        assert(native.set_deadline(2000000));
        assert(native.set_cwd("/updated", 77) == 0 && sends == 1);
    } else {
        const int fd = static_cast<int>(__xos_file_open("/fixture", O_RDWR));
        assert(fd == 3);
        xos_file_lease lease{};
        assert(__xos_file_lease_acquire(fd, 1, &lease) == 0);
        assert(native.set_deadline(1234567));
        failure = !std::strcmp(scenario, "native_deadline_reply") ? "wait_ready" : "wait_timeout";
        failure_armed = true;
        const auto result = native.write(lease.handle, "x", 1);
        const bool success = !std::strcmp(scenario, "native_deadline_reply");
        assert(result == (success ? 1 : xos::file::transport_timeout));
        assert(reply_waits == 1 && reply_deadline == 1234567 && sends == 2);
        failure_armed = false;
        assert(native.set_deadline(0));
        if (success) {
            assert(__xos_file_write(fd, "y", 1) == 1 && sends == 3);
            assert(__xos_file_lease_release(&lease) == 0 && __xos_file_close(fd) == 0);
        } else {
            assert(native.init());
            assert(native.write(lease.handle, "y", 1) == -7 && sends == 2);
            assert(__xos_file_write(fd, "z", 1) == -EIO && sends == 2);
        }
    }
}

int main(int argc, char** argv) {
    assert(argc == 2);
    if (!std::strcmp(argv[1], "basic")) basic();
    else if (!std::strcmp(argv[1], "bounds")) bounds();
    else if (!std::strcmp(argv[1], "access_legacy_stat")) access_legacy_stat();
    else if (!std::strcmp(argv[1], "spawn_cwd_serialization")) spawn_cwd_serialization();
    else if (!std::strcmp(argv[1], "concurrent")) concurrent();
    else if (!std::strcmp(argv[1], "inheritance") || !std::strcmp(argv[1], "inheritance_word_aligned")
             || !std::strcmp(argv[1], "invalid_inheritance")
             || !std::strcmp(argv[1], "duplicate_cleanup")) inheritance(argv[1]);
    else if (!std::strcmp(argv[1], "inheritance_v2") || !std::strcmp(argv[1], "duplicate_v2_handle")
             || !std::strcmp(argv[1], "path_v2_redirection")) inheritance_v2(argv[1]);
    else if (!std::strcmp(argv[1], "pipe_lease")) pipe_lease();
    else if (!std::strcmp(argv[1], "pipe_writev")) pipe_writev();
    else if (!std::strcmp(argv[1], "public_lease")) public_lease();
    else if (!std::strcmp(argv[1], "native_read_capacity")) native_read_capacity();
    else if (!std::strncmp(argv[1], "native_deadline_", 16)) native_deadline(argv[1]);
    else if (!std::strncmp(argv[1], "block_", 6)) block_bench(argv[1]);
    else if (!std::strncmp(argv[1], "anonymous_", 10)) anonymous_exchange(argv[1]);
    else if (!std::strncmp(argv[1], "directory_", 10)) directory_exchange(argv[1]);
    else if (!std::strcmp(argv[1], "wait_ready")) reply_ready(argv[1], 1, 0);
    else if (!std::strcmp(argv[1], "wait_spurious")) reply_ready(argv[1], 2, 0);
    else if (!std::strcmp(argv[1], "wait_legacy")) reply_ready(argv[1], 1, 1);
    else error_case(argv[1]);
    std::printf("PASS %s\n", argv[1]);
}
