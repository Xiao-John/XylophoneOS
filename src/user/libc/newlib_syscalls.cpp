// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#define _POSIX_C_SOURCE 200809L
#include <xos/file_client.hpp>
#include <xos/runtime_lock.hpp>
#include <xos/thread_abi.hpp>
#include <xos/elf.hpp>
#include <xos/execution.hpp>
#include <xos/libc_runtime.hpp>
#include <xos/sdk.hpp>
#include <xos/spawn.hpp>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <spawn.h>
#include <stdio.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/times.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef XOS_THREADED_RUNTIME
#include <sys/reent.h>
extern "C" void __env_lock(struct _reent*);
extern "C" void __env_unlock(struct _reent*);
#endif

using xos::i32;
using xos::u64;
using xos::u8;
using xos::u32;

struct __posix_spawnattr { short flags; };

namespace {
constexpr int fd_count = 32;
constexpr int object_count = 32;
constexpr int directory_count = 8;
constexpr int action_set_count = 4;
constexpr int action_count = 16;
constexpr int max_path = 256;
constexpr u32 heap_base = 0x60000000u;
constexpr u32 heap_limit = 0x70000000u;
constexpr u32 pipe_token_base = 65536u;

enum class object_kind : u8 { none, kernel, file, pipe_read, pipe_write };
struct open_object {
    object_kind kind;
    u32 references;
    bool close_on_exec;
    u32 handle;
    u32 flags;
    signed char stdio_source;
    char path[max_path];
};
struct fd_slot { signed char object; bool close_on_exec; };
struct directory_state {
    bool active;
    bool eof;
    char path[max_path];
    xos::file::entry entries[16];
    u32 count;
    u32 cursor;
    u32 position;
    struct dirent current;
};
enum class action_kind : u8 { open, close, dup2 };
struct spawn_action {
    action_kind kind;
    i32 first;
    i32 second;
    i32 flags;
    char path[max_path];
};
struct action_set {
    bool active;
    u32 count;
    spawn_action actions[action_count];
};
struct pipe_handles { u32 read_token; u32 write_token; };

xos::file::Client file_client;
bool runtime_ready;
char current_directory[max_path] = "/";
fd_slot descriptors[fd_count];
open_object objects[object_count];
directory_state directories[directory_count];
action_set action_sets[action_set_count];
using xos::libc::runtime_guard;
using xos::libc::runtime_mutex;
runtime_mutex fd_table_lock, object_locks[object_count], directory_lock, cwd_lock, spawn_lock, break_lock;


int error_from_file(xos::i64 result) {
    using xos::file::status;
    switch (static_cast<status>(result)) {
    case status::not_found: return ENOENT;
    case status::invalid: return EINVAL;
    case status::full: return EMFILE;
    case status::no_space: return ENOSPC;
    case status::busy: return EBUSY;
    case status::bad_handle: return EBADF;
    case status::would_block: return EAGAIN;
    case status::exists: return EEXIST;
    case status::io: return EIO;
    case status::ok: return 0;
    }
    return EIO;
}

struct executable_reader { u32 handle; };
bool read_executable(void* raw, u64 offset, u8* output, u32 length) {
    auto& reader = *static_cast<executable_reader*>(raw);
    if (offset > 0xffffffffu || file_client.seek(reader.handle, static_cast<u32>(offset)) < 0) {
        return false;
    }
    u32 done = 0;
    while (done < length) {
        const u32 count = length - done > xos::file::response_data_size
            ? xos::file::response_data_size : length - done;
        const xos::i64 got = file_client.read(reader.handle, output + done, count);
        if (got <= 0 || static_cast<u64>(got) > count) { return false; }
        done += static_cast<u32>(got);
    }
    return true;
}

int error_from_kernel(xos::i64 result) {
    if (result == xos::thread_error_busy || result == xos::process_error_state) { return EBUSY; }
    if (result == xos::thread_error_address) { return EFAULT; }
    if (result == xos::thread_error_timeout) { return ETIMEDOUT; }
    if (result == xos::thread_error_memory) { return ENOMEM; }
    if (result == xos::thread_error_unsupported) { return ENOTSUP; }
    if (result == -3) { return EAGAIN; }
    if (result == -7) { return EPIPE; }
    if (result == -1) { return EPERM; }
    if (result == -2) { return EINVAL; }
    if (result == -5) { return ENOMEM; }
    if (result == xos::process_error_delegation) { return EPERM; }
    return EIO;
}

int error_from_spawn(xos::i64 result) {
    switch (static_cast<xos::file::status>(result)) {
    case xos::file::status::not_found: return ENOENT;
    case xos::file::status::invalid: return ENOEXEC;
    case xos::file::status::full: return EMFILE;
    case xos::file::status::no_space: return ENOSPC;
    case xos::file::status::busy: return EBUSY;
    case xos::file::status::bad_handle: return EBADF;
    case xos::file::status::io: return EIO;
    case xos::file::status::would_block: return EAGAIN;
    case xos::file::status::exists: return EEXIST;
    case xos::file::status::ok: return 0;
    }
    return error_from_kernel(result);
}

bool copy_string(const char* source, char* target, u32 capacity) {
    if (source == nullptr || capacity == 0) { return false; }
    u32 i = 0;
    while (i + 1 < capacity && source[i] != '\0') {
        const u8 c = static_cast<u8>(source[i]);
        if (c < 0x20 || c > 0x7e) { return false; }
        target[i] = source[i];
        ++i;
    }
    if (source[i] != '\0') { return false; }
    target[i] = '\0';
    return true;
}

bool normalize_path(const char* path, char* output) {
    runtime_guard guard(cwd_lock);
    if (path == nullptr || output == nullptr) { return false; }
    char joined[max_path * 2];
    u32 used = 0;
    if (path[0] != '/') {
        for (u32 i = 0; current_directory[i] != '\0'; ++i) {
            if (used + 1 >= sizeof(joined)) { return false; }
            joined[used++] = current_directory[i];
        }
        if (used == 0 || joined[used - 1] != '/') { joined[used++] = '/'; }
    }
    for (u32 i = 0; path[i] != '\0'; ++i) {
        const u8 c = static_cast<u8>(path[i]);
        if (c < 0x20 || c > 0x7e || c == ':') { return false; }
        if (used + 1 >= sizeof(joined)) { return false; }
        joined[used++] = path[i];
    }
    if (used == 0) { joined[used++] = '/'; }
    joined[used] = '\0';
    u32 out = 0;
    output[out++] = '/';
    u32 i = 0;
    while (i < used) {
        while (i < used && joined[i] == '/') { ++i; }
        const u32 start = i;
        while (i < used && joined[i] != '/') { ++i; }
        const u32 length = i - start;
        if (length == 0 || (length == 1 && joined[start] == '.')) { continue; }
        if (length == 2 && joined[start] == '.' && joined[start + 1] == '.') {
            if (out > 1) {
                while (out > 1 && output[out - 1] != '/') { --out; }
                if (out > 1) { --out; }
            }
            continue;
        }
        if (out > 1) {
            if (out + 1 >= max_path) { return false; }
            output[out++] = '/';
        }
        if (out + length >= max_path) { return false; }
        for (u32 j = 0; j < length; ++j) { output[out++] = joined[start + j]; }
    }
    output[out] = '\0';
    return true;
}

// argv/environment are byte strings; filesystem paths retain their separate
// ASCII normalization contract. Newlines/tabs are valid shell -c arguments.
bool copy_argument(const char* source, char* target, u32 capacity) {
    if (!source || !target || !capacity) return false;
    for (u32 i = 0; i < capacity; ++i) {
        target[i] = source[i];
        if (!source[i]) return true;
    }
    return false;
}

int alloc_object(object_kind kind, u32 handle, u32 flags = 0) {
    runtime_guard guard(fd_table_lock);
    for (int i = 0; i < object_count; ++i) {
        if (objects[i].kind == object_kind::none) {
            objects[i].kind = kind;
            objects[i].references = 1;
            objects[i].close_on_exec = (flags & O_CLOEXEC) != 0;
            objects[i].handle = handle;
            objects[i].flags = flags;
            objects[i].stdio_source = -1;
            return i;
        }
    }
    return -1;
}

int alloc_fd(int minimum = 3) {
    for (int fd = minimum; fd < fd_count; ++fd) {
        if (descriptors[fd].object == -1) { return fd; }
    }
    return -1;
}

bool valid_fd(int fd) { return fd >= 0 && fd < fd_count && descriptors[fd].object >= 0; }

int release_object(int index) {
    open_object object{};
    {
        runtime_guard guard(fd_table_lock);
        if (index < 0 || index >= object_count || objects[index].kind == object_kind::none) { return 0; }
        if (--objects[index].references != 0) { return 0; }
        object = objects[index]; objects[index] = open_object{};
    }
    // No table lock while entering a service or allocator. Last close can be
    // deferred to an in-flight operation's pin release.
    switch (object.kind) {
    case object_kind::file: {
        const auto result = file_client.close(object.handle);
        if (result < 0) { errno = error_from_file(result); return -1; }
        break;
    }
    case object_kind::pipe_read: case object_kind::pipe_write:
        (void)xos::sdk::syscall(xos::sys_pipe_close, object.handle); break;
    case object_kind::kernel: (void)xos::sdk::close(object.handle); break;
    case object_kind::none: break;
    }
    return 0;
}
struct object_lease {
    int index = -1;
    explicit object_lease(int fd) {
        {
            runtime_guard guard(fd_table_lock);
            if (valid_fd(fd)) { index = descriptors[fd].object; ++objects[index].references; }
        }
        if (index >= 0) { object_locks[index].lock(); }
    }
    ~object_lease() {
        if (index >= 0) { object_locks[index].unlock(); release_object(index); }
    }
};
int close_fd(int fd) {
    int index;
    {
        runtime_guard guard(fd_table_lock);
        if (!valid_fd(fd)) { errno = EBADF; return -1; }
        index = descriptors[fd].object;
        descriptors[fd].object = -1; descriptors[fd].close_on_exec = false;
    }
    return release_object(index);
}

void close_runtime_descriptors() {
    for (int fd = 0; fd < fd_count; ++fd) {
        if (valid_fd(fd)) { (void)close_fd(fd); }
    }
}

int open_flags_to_file(int flags, u32& translated) {
    // File opens never acquire a controlling terminal. GCC's libcpp requests
    // O_NOCTTY even for ordinary source files.
    const int supported = O_ACCMODE | O_CREAT | O_EXCL | O_TRUNC | O_APPEND | O_CLOEXEC |
                          O_NOCTTY;
    if ((flags & ~supported) != 0) { return EINVAL; }
    const int access = flags & O_ACCMODE;
    if (access == O_RDONLY) { translated = xos::file::read_only; }
    else if (access == O_WRONLY) { translated = xos::file::write_only; }
    else if (access == O_RDWR) { translated = xos::file::read_write; }
    else { return EINVAL; }
    if ((flags & O_CREAT) != 0) { translated |= xos::file::open_create; }
    if ((flags & O_EXCL) != 0) { translated |= xos::file::open_exclusive; }
    if ((flags & O_TRUNC) != 0) { translated |= xos::file::open_truncate; }
    if ((flags & O_APPEND) != 0) { translated |= xos::file::open_append; }
    return 0;
}

int open_normalized(const char* path, int flags) {
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    u32 translated = 0;
    const int error = open_flags_to_file(flags, translated);
    if (error != 0) { errno = error; return -1; }
    int fd;
    {
        runtime_guard guard(fd_table_lock);
        fd = alloc_fd();
        if (fd < 0) { errno = EMFILE; return -1; }
        descriptors[fd].object = -2;
    }
    u32 handle = 0, size = 0, version = 0;
    const xos::i64 result = file_client.open(normalized, translated, handle, size, version);
    int object = -1;
    {
        runtime_guard guard(fd_table_lock);
        if (result == 0) { object = alloc_object(object_kind::file, handle, static_cast<u32>(flags)); }
        if (object >= 0) {
            memcpy(objects[object].path, normalized, strlen(normalized) + 1);
            descriptors[fd].object = static_cast<signed char>(object);
            descriptors[fd].close_on_exec = (flags & O_CLOEXEC) != 0;
        } else { descriptors[fd].object = -1; }
    }
    if (result != 0) { errno = error_from_file(result); return -1; }
    if (object < 0) { (void)file_client.close(handle); errno = EMFILE; return -1; }

    return fd;
}

void fill_stat(struct stat* output, u32 size, bool directory, u32 identity = 0) {
    memset(output, 0, sizeof(*output));
    output->st_dev = static_cast<dev_t>(1);
    output->st_ino = static_cast<ino_t>(identity);
    output->st_mode = static_cast<mode_t>((directory ? S_IFDIR : S_IFREG) | 0777);
    output->st_nlink = 1;
    output->st_size = static_cast<off_t>(size);
    output->st_blksize = 512;
    output->st_blocks = static_cast<blkcnt_t>((static_cast<u64>(size) + 511u) / 512u);
}

directory_state* get_directory(DIR* directory) {
    for (int i = 0; i < directory_count; ++i) {
        if (reinterpret_cast<DIR*>(&directories[i]) == directory && directories[i].active) {
            return &directories[i];
        }
    }
    return nullptr;
}

int spawn_action_set(const posix_spawn_file_actions_t* opaque, action_set*& result) {
    result = nullptr;
    if (opaque == nullptr || *opaque == nullptr) { return 0; }
    for (int i = 0; i < action_set_count; ++i) {
        if (reinterpret_cast<posix_spawn_file_actions_t>(&action_sets[i]) == *opaque &&
            action_sets[i].active) {
            result = &action_sets[i];
            return 0;
        }
    }
    return EINVAL;
}

int append_action(posix_spawn_file_actions_t* opaque, const spawn_action& action) {
    runtime_guard guard(spawn_lock);
    if (opaque == nullptr || *opaque == nullptr) { return EINVAL; }
    action_set* set = nullptr;
    for (int i = 0; i < action_set_count; ++i) {
        if (reinterpret_cast<posix_spawn_file_actions_t>(&action_sets[i]) == *opaque &&
            action_sets[i].active) { set = &action_sets[i]; break; }
    }
    if (set == nullptr) { return EINVAL; }
    if (set->count >= action_count) { return E2BIG; }
    set->actions[set->count++] = action;
    return 0;
}
}

char** environ;

static int restore_exec_descriptors(const xos::startup_info* startup) {
    const auto* extension = reinterpret_cast<const xos::startup_exec_extension*>(
        reinterpret_cast<const u8*>(startup) + xos::startup_exec_offset);
    const u64 start = xos::process_startup_begin, end = xos::process_stack_top;
    const u64 bytes = static_cast<u64>(extension->count) * sizeof(xos::startup_descriptor);
    if (startup->version != 3 || extension->magic != xos::startup_exec_magic ||
        extension->reserved || extension->count > fd_count || extension->descriptors < start ||
        extension->descriptors > end || bytes > end - extension->descriptors) { errno = EINVAL; return -1; }
    const auto* list = reinterpret_cast<const xos::startup_descriptor*>(extension->descriptors);
    // Initial stdio objects only borrow the kernel routes. Rebuild the whole FD
    // table without releasing routes that non-CLOEXEC aliases still own.
    for (auto& fd : descriptors) { fd = {-1, false}; }
    for (auto& object : objects) object = open_object{};
    for (u32 i = 0; i < extension->count; ++i) {
        const auto& item = list[i];
        if (item.object >= object_count || item.kind < 1 || item.kind > 4 || item.reserved ||
            (item.fd != 0xffffffffu && item.fd >= fd_count)) { errno = EINVAL; return -1; }
        if (item.fd == 0xffffffffu) continue;
        if (valid_fd(static_cast<int>(item.fd))) { errno = EINVAL; return -1; }
        auto& object = objects[item.object];
        const auto kind = static_cast<object_kind>(item.kind);
        if (object.kind == object_kind::none) {
            object.kind = kind; object.handle = item.handle; object.flags = item.flags;
            object.stdio_source = kind == object_kind::kernel ? static_cast<signed char>(item.handle) : -1;
        } else if (object.kind != kind || object.handle != item.handle || object.flags != item.flags) {
            errno = EINVAL; return -1;
        }
        ++object.references;
        descriptors[item.fd] = {static_cast<signed char>(item.object), false};
    }
    for (u32 i = 0; i < extension->count; ++i) {
        const auto& item = list[i];
        if (item.fd != 0xffffffffu) continue;
        if (objects[item.object].kind != object_kind::none) { errno = EINVAL; return -1; }
        xos::i64 result;
        const auto kind = static_cast<object_kind>(item.kind);
        if (kind == object_kind::file) result = file_client.close(item.handle);
        else if (kind == object_kind::kernel) result = xos::sdk::close(item.handle);
        else result = xos::sdk::syscall(xos::sys_pipe_close, item.handle);
        if (result < 0) {
            // Already committed: the FD is closed in the new table, and the
            // service retries deferred I/O cleanup. Never return to old code.
            const int saved = errno;
            const char message[] = "xos: exec descriptor cleanup deferred\n";
            (void)write(2, message, sizeof(message)-1); errno = saved;
        }
    }
    return 0;
}

extern "C" int xos_libc_init(const xos::startup_info* startup) {
    if (startup == nullptr || !file_client.init()) { errno = EIO; return -1; }
    for (int i = 0; i < fd_count; ++i) {
        descriptors[i] = fd_slot{};
        descriptors[i].object = -1;
    }
    for (int i = 0; i < object_count; ++i) { objects[i] = open_object{}; }
    for (int i = 0; i < directory_count; ++i) { directories[i] = directory_state{}; }
    for (int i = 0; i < action_set_count; ++i) { action_sets[i] = action_set{}; }
    const xos::startup_extension* extension = nullptr;
    if (startup->reserved == xos::startup_extension_offset && startup->version >= 2) {
        extension = reinterpret_cast<const xos::startup_extension*>(
            reinterpret_cast<const u8*>(startup) + xos::startup_extension_offset);
        if (extension->magic != xos::startup_extension_magic ||
            extension->environment_count > xos::startup_environment_max) {
            errno = EINVAL; return -1;
        }
    }
    for (int fd = 0; fd < 3; ++fd) {
        if (extension != nullptr && (extension->flags & (1u << fd)) != 0) { continue; }
        const int object = alloc_object(object_kind::kernel, startup->handles[fd], fd == 0 ? O_RDONLY : O_WRONLY);
        if (object < 0) { errno = EMFILE; return -1; }
        descriptors[fd].object = static_cast<signed char>(object);
        descriptors[fd].close_on_exec = false;
        objects[object].stdio_source = static_cast<signed char>(fd);
    }
    current_directory[0] = '/'; current_directory[1] = '\0';
    environ = nullptr;
    runtime_ready = true;
    if (extension != nullptr) {
        if (extension->working_directory != 0 &&
            !copy_string(reinterpret_cast<const char*>(extension->working_directory),
                         current_directory, sizeof(current_directory))) {
            errno = EINVAL; return -1;
        }
        environ = reinterpret_cast<char**>(extension->environment);
        if (startup->version >= 3) return restore_exec_descriptors(startup);
        for (int fd = 0; fd < 3; ++fd) {
            if ((extension->flags & (1u << (8 + fd))) != 0) {
                if (extension->file_handles[fd] == 0) { errno = EINVAL; return -1; }
                const int inherited = alloc_object(object_kind::file,
                    extension->file_handles[fd], extension->open_flags[fd]);
                if (inherited < 0) { errno = EMFILE; return -1; }
                if (valid_fd(fd)) {
                    const int old_object = descriptors[fd].object;
                    if (objects[old_object].kind == object_kind::kernel) {
                        objects[old_object] = open_object{};
                        descriptors[fd].object = -1;
                    } else { (void)close_fd(fd); }
                }
                descriptors[fd].object = static_cast<signed char>(inherited);
                descriptors[fd].close_on_exec = false;
                continue;
            }
            if (extension->open_paths[fd] == 0) { continue; }
            const char* path = reinterpret_cast<const char*>(extension->open_paths[fd]);
            const int opened = open_normalized(path, static_cast<int>(extension->open_flags[fd]));
            if (opened < 0) { return -1; }
            if ((extension->open_flags[fd] & O_CLOEXEC) != 0) {
                (void)close_fd(opened);
                if (valid_fd(fd)) {
                    const int old_object = descriptors[fd].object;
                    if (objects[old_object].kind == object_kind::kernel) {
                        objects[old_object] = open_object{};
                        descriptors[fd].object = -1;
                    } else { (void)close_fd(fd); }
                }
                continue;
            }
            const int source_object = descriptors[opened].object;
            if (valid_fd(fd)) {
                const int old_object = descriptors[fd].object;
                if (objects[old_object].kind == object_kind::kernel) {
                    // Startup handles are borrowed routes. Keep the kernel reference alive
                    // for the lifetime of the task even when stdio is redirected to a file.
                    objects[old_object] = open_object{};
                    descriptors[fd].object = -1;
                } else { (void)close_fd(fd); }
            }
            descriptors[fd].object = static_cast<signed char>(source_object);
            descriptors[fd].close_on_exec = false;
            descriptors[opened].object = -1;
        }
    }
    return 0;
}

extern "C" void xos_libc_finish() {
    (void)fflush(nullptr);
    close_runtime_descriptors();
    runtime_ready = false;
}

extern "C" void* _sbrk(ptrdiff_t increment) {
    runtime_guard guard(break_lock);
    const xos::i64 current = xos::sdk::syscall(xos::sys_heap_break, 0);
    if (current < static_cast<xos::i64>(heap_base) || current > static_cast<xos::i64>(heap_limit)) {
        errno = ENOMEM; return reinterpret_cast<void*>(-1);
    }
    if (increment < static_cast<xos::i64>(heap_base) - current ||
        increment > static_cast<xos::i64>(heap_limit) - current) {
        errno = ENOMEM; return reinterpret_cast<void*>(-1);
    }
    const xos::i64 requested = current + increment;
    const xos::i64 result = xos::sdk::syscall(xos::sys_heap_break, static_cast<xos::u64>(requested));
    if (result < 0) { errno = error_from_kernel(result); return reinterpret_cast<void*>(-1); }
    return reinterpret_cast<void*>(static_cast<xos::u64>(current));
}

extern "C" void* sbrk(ptrdiff_t increment) { return _sbrk(increment); }

extern "C" int open(const char* path, int flags, ...) {
    if (!runtime_ready) { errno = EIO; return -1; }
    return open_normalized(path, flags);
}

extern "C" int _open(const char* path, int flags, int) { return open(path, flags); }

extern "C" int close(int fd) { return close_fd(fd); }

extern "C" _READ_WRITE_RETURN_TYPE read(int fd, void* buffer, size_t length) {
    object_lease lease(fd);
    if (lease.index < 0) { errno = EBADF; return -1; }
    if (buffer == nullptr && length != 0) { errno = EFAULT; return -1; }
    if (length == 0) { return 0; }
    if (length > static_cast<size_t>(INT_MAX)) { length = static_cast<size_t>(INT_MAX); }
    open_object& object = objects[lease.index];
    if (object.kind == object_kind::file) {
        if ((object.flags & O_ACCMODE) == O_WRONLY) { errno = EBADF; return -1; }
        const u32 chunk = length > xos::file::response_data_size
                              ? xos::file::response_data_size : static_cast<u32>(length);
        const xos::i64 result = file_client.read(object.handle, buffer, chunk);
        if (result < 0) { errno = error_from_file(result); return -1; }
        return static_cast<ssize_t>(result);
    }
    if (object.kind == object_kind::kernel || object.kind == object_kind::pipe_read) {
        for (;;) {
            const xos::i64 result = object.kind == object_kind::kernel
                ? xos::sdk::read(object.handle, buffer, length)
                : xos::sdk::syscall(xos::sys_pipe_read, object.handle,
                                    reinterpret_cast<xos::u64>(buffer), length);
            if (result != xos::process_error_would_block) {
                if (result < 0) { errno = error_from_kernel(result); return -1; }
                return static_cast<ssize_t>(result);
            }
            const xos::i64 waited = xos::sdk::syscall(xos::sys_pipe_wait, object.handle);
            if (waited < 0) {
                // The original nonblocking console behavior is preserved.
                errno = waited == xos::process_error_would_block ? EAGAIN : error_from_kernel(waited);
                return -1;
            }
        }
    }
    errno = EBADF; return -1;
}

extern "C" _READ_WRITE_RETURN_TYPE write(int fd, const void* buffer, size_t length) {
    object_lease lease(fd);
    if (lease.index < 0) { errno = EBADF; return -1; }
    if (buffer == nullptr && length != 0) { errno = EFAULT; return -1; }
    if (length == 0) { return 0; }
    if (length > static_cast<size_t>(INT_MAX)) { length = static_cast<size_t>(INT_MAX); }
    open_object& object = objects[lease.index];
    if (object.kind == object_kind::file) {
        if ((object.flags & O_ACCMODE) == O_RDONLY) { errno = EBADF; return -1; }
        size_t done = 0;
        while (done < length) {
            const size_t remaining = length - done;
            const u32 chunk = remaining > xos::file::request_data_size
                                  ? xos::file::request_data_size : static_cast<u32>(remaining);
            const xos::i64 result = file_client.write(
                object.handle, static_cast<const u8*>(buffer) + done, chunk);
            if (result < 0) {
                errno = error_from_file(result);
                if (done == 0) { return -1; }
                return static_cast<ssize_t>(done);
            }
            if (result == 0) {
                errno = EIO;
                if (done == 0) { return -1; }
                return static_cast<ssize_t>(done);
            }
            done += static_cast<size_t>(result);
        }
        return static_cast<ssize_t>(done);
    }
    if (object.kind == object_kind::kernel || object.kind == object_kind::pipe_write) {
        const bool console = object.kind == object_kind::kernel &&
            xos::sdk::syscall(xos::sys_process_stdio, 0, object.handle) != 0;
        const size_t chunk = console && length > 256 ? 256 : length;
        for (;;) {
            const xos::i64 result = object.kind == object_kind::kernel
                ? xos::sdk::write(object.handle, buffer, chunk)
                : xos::sdk::syscall(xos::sys_pipe_write, object.handle,
                                    reinterpret_cast<xos::u64>(buffer), chunk);
            if (result != xos::process_error_would_block) {
                if (result < 0) { errno = error_from_kernel(result); return -1; }
                return static_cast<ssize_t>(result);
            }
            const xos::i64 waited = xos::sdk::syscall(xos::sys_pipe_wait, object.handle,
                chunk <= xos::process_pipe_bytes ? chunk : 1);
            if (waited < 0) {
                errno = waited == xos::process_error_would_block ? EAGAIN : error_from_kernel(waited);
                return -1;
            }
        }
    }
    errno = EBADF; return -1;
}

extern "C" off_t lseek(int fd, off_t offset, int whence) {
    object_lease lease(fd);
    if (lease.index < 0) { errno = EBADF; return -1; }
    open_object& object = objects[lease.index];
    if (object.kind != object_kind::file) { errno = ESPIPE; return static_cast<off_t>(-1); }
    u32 origin = xos::file::seek_set;
    if (whence == SEEK_CUR) { origin = xos::file::seek_current; }
    else if (whence == SEEK_END) { origin = xos::file::seek_end; }
    else if (whence != SEEK_SET) { errno = EINVAL; return static_cast<off_t>(-1); }
    const xos::i64 result = file_client.seek(object.handle, static_cast<xos::i64>(offset), origin);
    if (result < 0) { errno = error_from_file(result); return static_cast<off_t>(-1); }
    return static_cast<off_t>(result);
}

extern "C" int stat(const char* path, struct stat* status) {
    if (status == nullptr) { errno = EFAULT; return -1; }
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    u32 size = 0, attributes = 0, identity = 0;
    const xos::i64 result = file_client.stat_info(normalized, size, attributes, identity);
    if (result != 0) { errno = error_from_file(result); return -1; }
    fill_stat(status, size, (attributes & xos::file::stat_is_directory) != 0, identity);
    return 0;
}

extern "C" int access(const char* path, int mode) {
    if ((mode & ~(F_OK | R_OK | W_OK | X_OK)) != 0) { errno = EINVAL; return -1; }
    struct stat status{};
    if (stat(path, &status) != 0) { return -1; }
    // FAT32 access is uniform. XOS execution requires a supported ELF image,
    // not a stored POSIX mode bit. Pin and validate the same bytes as the loader.
    if ((mode & X_OK) != 0 && !S_ISDIR(status.st_mode)) {
        char normalized[max_path];
        if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
        u32 handle = 0, size = 0, version = 0;
        const xos::i64 opened = file_client.open(normalized, xos::file::read_only, handle, size, version);
        if (opened < 0) { errno = error_from_file(opened); return -1; }
        executable_reader reader{handle};
        xos::elf::load_plan plan{};
        const auto inspected = xos::elf::inspect_reader(read_executable, &reader, size,
                                                        xos::sdk::target_elf_machine(), plan);
        const xos::i64 closed = file_client.close(handle);
        if (closed < 0) { errno = error_from_file(closed); return -1; }
        if (inspected != xos::elf::error::none) {
            errno = inspected == xos::elf::error::io ? EIO : EACCES;
            return -1;
        }
    }
    return 0;
}

extern "C" long sysconf(int name) {
    switch (name) {
    case _SC_OPEN_MAX: return fd_count;
    case _SC_PAGESIZE: return 4096;
    case _SC_ARG_MAX: return 64 * 256;
    default: errno = EINVAL; return -1;
    }
}

extern "C" int gettimeofday(struct timeval*, void*) {
    errno = ENOSYS;
    return -1;
}
extern "C" int _gettimeofday(struct timeval* value, void* zone) {
    return gettimeofday(value, zone);
}

extern "C" int fstat(int fd, struct stat* status) {
    object_lease lease(fd);
    if (lease.index < 0) { errno = EBADF; return -1; }
    if (status == nullptr) { errno = EFAULT; return -1; }
    const open_object& object = objects[lease.index];
    if (object.kind == object_kind::kernel) {
        fill_stat(status, 0, false); status->st_mode = S_IFCHR | 0666; return 0;
    }
    if (object.kind == object_kind::pipe_read || object.kind == object_kind::pipe_write) {
        fill_stat(status, 0, false); status->st_mode = S_IFIFO | 0666; return 0;
    }
    if (object.kind != object_kind::file) { errno = EBADF; return -1; }
    u32 size = 0, attributes = 0, identity = 0;
    const xos::i64 result = file_client.fstat(object.handle, size, attributes, identity);
    if (result != 0) { errno = error_from_file(result); return -1; }
    fill_stat(status, size, (attributes & xos::file::stat_is_directory) != 0, identity);
    return 0;
}

extern "C" int unlink(const char* path) {
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    u32 size = 0, attributes = 0;
    const xos::i64 stat_result = file_client.stat_info(normalized, size, attributes);
    (void)size;
    if (stat_result != 0) { errno = error_from_file(stat_result); return -1; }
    if ((attributes & xos::file::stat_is_directory) != 0) { errno = EISDIR; return -1; }
    const xos::i64 result = file_client.remove(normalized);
    if (result != 0) { errno = error_from_file(result); return -1; }
    return 0;
}
extern "C" int _unlink(const char* path) { return unlink(path); }

extern "C" int rmdir(const char* path) {
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    u32 size = 0, attributes = 0;
    const xos::i64 stat_result = file_client.stat_info(normalized, size, attributes);
    (void)size;
    if (stat_result != 0) { errno = error_from_file(stat_result); return -1; }
    if ((attributes & xos::file::stat_is_directory) == 0) { errno = ENOTDIR; return -1; }
    // FatFs reports a non-empty directory as FR_DENIED; the service currently
    // maps that coarse result to EINVAL rather than a distinct ENOTEMPTY.
    const xos::i64 result = file_client.remove(normalized);
    if (result != 0) { errno = error_from_file(result); return -1; }
    return 0;
}

extern "C" int rename(const char* old_path, const char* new_path) {
    char old_normalized[max_path], new_normalized[max_path];
    if (!normalize_path(old_path, old_normalized) || !normalize_path(new_path, new_normalized)) {
        errno = ENAMETOOLONG; return -1;
    }
    const xos::i64 result = file_client.rename(old_normalized, new_normalized);
    if (result != 0) { errno = error_from_file(result); return -1; }
    return 0;
}
extern "C" int _rename(const char* old_path, const char* new_path) { return rename(old_path, new_path); }

extern "C" int mkdir(const char* path, mode_t) {
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    const xos::i64 result = file_client.mkdir(normalized);
    if (result != 0) { errno = error_from_file(result); return -1; }
    return 0;
}
extern "C" int _mkdir(const char* path, mode_t mode) { return mkdir(path, mode); }

extern "C" char* getcwd(char* buffer, size_t size) {
    char snapshot[max_path];
    { runtime_guard guard(cwd_lock); memcpy(snapshot, current_directory, max_path); }
    const size_t length = strlen(snapshot) + 1;
    if (buffer == nullptr) {
        if (size != 0) { errno = EINVAL; return nullptr; }
        buffer = static_cast<char*>(malloc(length));
        if (buffer == nullptr) { errno = ENOMEM; return nullptr; }
        size = length;
    }
    if (size < length) { errno = ERANGE; return nullptr; }
    memcpy(buffer, snapshot, length);
    return buffer;
}

extern "C" int chdir(const char* path) {
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    u32 size = 0, attributes = 0;
    const xos::i64 result = file_client.stat_info(normalized, size, attributes);
    (void)size;
    if (result != 0) { errno = error_from_file(result); return -1; }
    if ((attributes & xos::file::stat_is_directory) == 0) { errno = ENOTDIR; return -1; }
    { runtime_guard guard(cwd_lock); memcpy(current_directory, normalized, strlen(normalized) + 1); }
    return 0;
}

extern "C" int dup2(int old_fd, int new_fd) {
    int previous = -1;
    {
        runtime_guard guard(fd_table_lock);
        if (!valid_fd(old_fd) || new_fd < 0 || new_fd >= fd_count) { errno = EBADF; return -1; }
        if (old_fd == new_fd) { return new_fd; }
        if (descriptors[new_fd].object == -2) { errno = EBUSY; return -1; }
        if (valid_fd(new_fd)) { previous = descriptors[new_fd].object; }
        const int index = descriptors[old_fd].object;
        ++objects[index].references;
        descriptors[new_fd].object = static_cast<signed char>(index);
        descriptors[new_fd].close_on_exec = false;
    }
    if (previous >= 0) { release_object(previous); }
    return new_fd;
}

extern "C" int dup(int fd) {
    runtime_guard guard(fd_table_lock);
    if (!valid_fd(fd)) { errno = EBADF; return -1; }
    const int duplicate = alloc_fd(0);
    if (duplicate < 0) { errno = EMFILE; return -1; }
    const int index = descriptors[fd].object;
    if (objects[index].references == 0xff) { errno = EMFILE; return -1; }
    ++objects[index].references;
    descriptors[duplicate].object = static_cast<signed char>(index);
    descriptors[duplicate].close_on_exec = false;
    return duplicate;
}

extern "C" int fcntl(int fd, int command, ...) {
    runtime_guard guard(fd_table_lock);
    if (!valid_fd(fd)) { errno = EBADF; return -1; }
    va_list arguments;
    va_start(arguments, command);
    int result = -1;
    if (command == F_GETFD) {
        result = descriptors[fd].close_on_exec ? FD_CLOEXEC : 0;
    } else if (command == F_SETFD) {
        const int value = va_arg(arguments, int);
        if ((value & ~FD_CLOEXEC) != 0) { errno = EINVAL; }
        else { descriptors[fd].close_on_exec = (value & FD_CLOEXEC) != 0; result = 0; }
    } else if (command == F_GETFL) {
        result = static_cast<int>(objects[descriptors[fd].object].flags);
    } else if (command == F_SETFL) {
        const int value = va_arg(arguments, int);
        if ((value & ~(O_ACCMODE | O_APPEND)) != 0 ||
            ((value ^ static_cast<int>(objects[descriptors[fd].object].flags)) & O_APPEND) != 0) {
            errno = ENOTSUP;
        } else { result = 0; }
    } else if (command == F_DUPFD
#ifdef F_DUPFD_CLOEXEC
               || command == F_DUPFD_CLOEXEC
#endif
    ) {
        const int minimum = va_arg(arguments, int);
        if (minimum < 0 || minimum >= fd_count) { errno = EINVAL; }
        else {
            const int duplicate = alloc_fd(minimum);
            if (duplicate < 0) { errno = EMFILE; }
            else {
                const int index = descriptors[fd].object;
                if (objects[index].references == 0xff) { errno = EMFILE; }
                else {
                    ++objects[index].references;
                    descriptors[duplicate].object = static_cast<signed char>(index);
                    descriptors[duplicate].close_on_exec = false;
#ifdef F_DUPFD_CLOEXEC
                    if (command == F_DUPFD_CLOEXEC) { descriptors[duplicate].close_on_exec = true; }
#endif
                    result = duplicate;
                }
            }
        }
    } else { errno = EINVAL; }
    va_end(arguments);
    return result;
}

extern "C" int pipe(int output[2]) {
    runtime_guard guard(fd_table_lock);
    if (output == nullptr) { errno = EFAULT; return -1; }
    const int read_fd = alloc_fd();
    if (read_fd < 0) { errno = EMFILE; return -1; }
    int write_fd = -1;
    for (int fd = read_fd + 1; fd < fd_count; ++fd) {
        if (descriptors[fd].object == -1) { write_fd = fd; break; }
    }
    if (write_fd < 0) { errno = EMFILE; return -1; }
    pipe_handles handles{};
    const xos::i64 result = xos::sdk::syscall(xos::sys_pipe_create, reinterpret_cast<xos::u64>(&handles));
    if (result < 0 || handles.read_token < pipe_token_base || handles.write_token < pipe_token_base) {
        errno = error_from_kernel(result); return -1;
    }
    const int read_object = alloc_object(object_kind::pipe_read, handles.read_token);
    const int write_object = alloc_object(object_kind::pipe_write, handles.write_token, O_WRONLY);
    if (read_object < 0 || write_object < 0) {
        if (read_object >= 0) { release_object(read_object); }
        else { (void)xos::sdk::syscall(xos::sys_pipe_close, handles.read_token); }
        if (write_object >= 0) { release_object(write_object); }
        else { (void)xos::sdk::syscall(xos::sys_pipe_close, handles.write_token); }
        errno = EMFILE; return -1;
    }
    descriptors[read_fd].object = static_cast<signed char>(read_object);
    descriptors[write_fd].object = static_cast<signed char>(write_object);
    descriptors[read_fd].close_on_exec = false;
    descriptors[write_fd].close_on_exec = false;
    output[0] = read_fd; output[1] = write_fd;
    return 0;
}

extern "C" int isatty(int fd) {
    runtime_guard guard(fd_table_lock);
    if (!valid_fd(fd)) { errno = EBADF; return 0; }
    const auto& object = objects[descriptors[fd].object];
    if (object.kind != object_kind::kernel) { errno = ENOTTY; return 0; }
    const auto result = xos::sdk::syscall(xos::sys_process_stdio, 0, object.handle);
    if (result != 1) { errno = ENOTTY; return 0; }
    return 1;
}

extern "C" DIR* opendir(const char* path) {
    runtime_guard guard(directory_lock);
    char normalized[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return nullptr; }
    u32 size = 0, attributes = 0;
    const xos::i64 stat_result = file_client.stat_info(normalized, size, attributes);
    (void)size;
    if (stat_result != 0) { errno = error_from_file(stat_result); return nullptr; }
    if ((attributes & xos::file::stat_is_directory) == 0) { errno = ENOTDIR; return nullptr; }
    directory_state* state = nullptr;
    for (int i = 0; i < directory_count; ++i) {
        if (!directories[i].active) { state = &directories[i]; break; }
    }
    if (state == nullptr) { errno = EMFILE; return nullptr; }
    *state = directory_state{};
    state->active = true;
    memcpy(state->path, normalized, strlen(normalized) + 1);
    return reinterpret_cast<DIR*>(state);
}

extern "C" struct dirent* readdir(DIR* directory) {
    runtime_guard guard(directory_lock);
    directory_state* state = get_directory(directory);
    if (state == nullptr) { errno = EBADF; return nullptr; }
    while (state->position >= state->count && !state->eof) {
        state->count = 0;
        xos::i64 result = file_client.list(state->path, state->entries, 16,
                                          state->count, state->cursor);
        if (result != 0) { errno = error_from_file(result); return nullptr; }
        state->position = 0;
        state->eof = state->cursor == 0;
    }
    if (state->eof && state->position >= state->count) { return nullptr; }
    const xos::file::entry& entry = state->entries[state->position++];
    memset(&state->current, 0, sizeof(state->current));
    memcpy(state->current.d_name, entry.name, strlen(entry.name) + 1);
    state->current.d_type = entry.directory ? DT_DIR : DT_REG;
    return &state->current;
}

extern "C" int closedir(DIR* directory) {
    runtime_guard guard(directory_lock);
    directory_state* state = get_directory(directory);
    if (state == nullptr) { errno = EBADF; return -1; }
    *state = directory_state{};
    return 0;
}

extern "C" void rewinddir(DIR* directory) {
    runtime_guard guard(directory_lock);
    directory_state* state = get_directory(directory);
    if (state == nullptr) { errno = EBADF; return; }
    state->cursor = 0; state->position = 0; state->count = 0; state->eof = false;
}

extern "C" int posix_spawn_file_actions_init(posix_spawn_file_actions_t* output) {
    runtime_guard guard(spawn_lock);
    if (output == nullptr) { return EINVAL; }
    for (int i = 0; i < action_set_count; ++i) {
        if (!action_sets[i].active) {
            action_sets[i] = action_set{};
            action_sets[i].active = true;
            *output = reinterpret_cast<posix_spawn_file_actions_t>(&action_sets[i]);
            return 0;
        }
    }
    return EAGAIN;
}

extern "C" int posix_spawn_file_actions_destroy(posix_spawn_file_actions_t* opaque) {
    runtime_guard guard(spawn_lock);
    if (opaque == nullptr || *opaque == nullptr) { return EINVAL; }
    action_set* set = nullptr;
    const int error = spawn_action_set(opaque, set);
    if (error != 0) { return error; }
    *set = action_set{}; *opaque = nullptr;
    return 0;
}

extern "C" int posix_spawn_file_actions_addopen(posix_spawn_file_actions_t* opaque,
                                                    int fd, const char* path,
                                                    int flags, mode_t) {
    if (fd < 0 || fd >= 3) { return ENOTSUP; }
    spawn_action action{}; action.kind = action_kind::open; action.first = fd; action.flags = flags;
    char normalized[max_path];
    if (!normalize_path(path, normalized) || !copy_string(normalized, action.path, max_path)) { return ENAMETOOLONG; }
    u32 translated = 0;
    const int error = open_flags_to_file(flags, translated);
    if (error != 0) { return error; }
    return append_action(opaque, action);
}

extern "C" int posix_spawn_file_actions_addclose(posix_spawn_file_actions_t* opaque, int fd) {
    if (fd < 0 || fd >= fd_count) { return ENOTSUP; }
    // Non-stdio descriptors are never inherited by the current process ABI.
    if (fd >= 3) {
        if (!valid_fd(fd)) { return EBADF; }
        action_set* set = nullptr;
        const int error = spawn_action_set(opaque, set);
        return error;
    }
    spawn_action action{}; action.kind = action_kind::close; action.first = fd;
    return append_action(opaque, action);
}

extern "C" int posix_spawn_file_actions_adddup2(posix_spawn_file_actions_t* opaque,
                                                  int old_fd, int new_fd) {
    if (old_fd < 0 || old_fd >= fd_count || new_fd < 0 || new_fd >= 3) { return ENOTSUP; }
    spawn_action action{}; action.kind = action_kind::dup2; action.first = old_fd; action.second = new_fd;
    return append_action(opaque, action);
}

extern "C" int posix_spawnattr_init(posix_spawnattr_t* output) {
    if (output == nullptr) { return EINVAL; }
    auto* attributes = static_cast<__posix_spawnattr*>(malloc(sizeof(__posix_spawnattr)));
    if (attributes == nullptr) { return ENOMEM; }
    attributes->flags = 0;
    *output = reinterpret_cast<posix_spawnattr_t>(attributes);
    return 0;
}

extern "C" int posix_spawnattr_destroy(posix_spawnattr_t* opaque) {
    if (opaque == nullptr || *opaque == nullptr) { return EINVAL; }
    free(*opaque); *opaque = nullptr; return 0;
}

extern "C" int posix_spawnattr_getflags(const posix_spawnattr_t* opaque, short* flags) {
    if (opaque == nullptr || *opaque == nullptr || flags == nullptr) { return EINVAL; }
    *flags = reinterpret_cast<const __posix_spawnattr*>(*opaque)->flags; return 0;
}

extern "C" int posix_spawnattr_setflags(posix_spawnattr_t* opaque, short flags) {
    if (opaque == nullptr || *opaque == nullptr) { return EINVAL; }
    if (flags != 0) { return ENOTSUP; }
    reinterpret_cast<__posix_spawnattr*>(*opaque)->flags = flags; return 0;
}

extern "C" int posix_spawnattr_getpgroup(const posix_spawnattr_t*, pid_t*) { return ENOTSUP; }
extern "C" int posix_spawnattr_getschedparam(const posix_spawnattr_t*, struct sched_param*) { return ENOTSUP; }
extern "C" int posix_spawnattr_getschedpolicy(const posix_spawnattr_t*, int*) { return ENOTSUP; }
extern "C" int posix_spawnattr_getsigdefault(const posix_spawnattr_t*, sigset_t*) { return ENOTSUP; }
extern "C" int posix_spawnattr_getsigmask(const posix_spawnattr_t*, sigset_t*) { return ENOTSUP; }
extern "C" int posix_spawnattr_setpgroup(posix_spawnattr_t*, pid_t) { return ENOTSUP; }
extern "C" int posix_spawnattr_setschedparam(posix_spawnattr_t*, const struct sched_param*) { return ENOTSUP; }
extern "C" int posix_spawnattr_setschedpolicy(posix_spawnattr_t*, int) { return ENOTSUP; }
extern "C" int posix_spawnattr_setsigdefault(posix_spawnattr_t*, const sigset_t*) { return ENOTSUP; }
extern "C" int posix_spawnattr_setsigmask(posix_spawnattr_t*, const sigset_t*) { return ENOTSUP; }

static int posix_spawn_with_depth(pid_t* output_pid, const char* path,
                                  const posix_spawn_file_actions_t* actions,
                                  const posix_spawnattr_t* attributes,
                                  char* const argv[], char* const envp[],
                                  u32 delegate_spawn_depth) {
    runtime_guard spawn_guard(spawn_lock);
    struct spawn_snapshot {
        fd_slot fds[fd_count];
        open_object open[object_count + action_count]{};
        bool pinned[object_count]{};
        spawn_snapshot(const spawn_snapshot&) = delete;
        spawn_snapshot& operator=(const spawn_snapshot&) = delete;
        spawn_snapshot() {
            runtime_guard guard(fd_table_lock);
            memcpy(fds, descriptors, sizeof(fds)); memcpy(open, objects, sizeof(objects));
            for (auto& fd : fds) {
                if (fd.object >= 0 && !pinned[fd.object]) { pinned[fd.object] = true; ++objects[fd.object].references; }
            }
        }
        ~spawn_snapshot() {
            for (int i = 0; i < object_count; ++i) { if (pinned[i]) { release_object(i); } }
            for (int i = object_count; i < object_count + action_count; ++i) {
                if (open[i].kind == object_kind::file) { (void)file_client.close(open[i].handle); }
            }
        }
        void assign(int fd, int object, bool cloexec = false) {
            const int previous = fds[fd].object;
            fds[fd].object = static_cast<signed char>(object);
            fds[fd].close_on_exec = cloexec;
            if (previous >= object_count) {
                bool used = false;
                for (const auto& entry : fds) { used = used || entry.object == previous; }
                if (!used) { (void)file_client.close(open[previous].handle); open[previous] = open_object{}; }
            }
        }
        int open_action(const spawn_action& action) {
            int index = object_count;
            while (index < object_count + action_count && open[index].kind != object_kind::none) { ++index; }
            if (index == object_count + action_count) { return EMFILE; }
            char path[max_path];
            if (!normalize_path(action.path, path)) { return ENAMETOOLONG; }
            u32 flags = 0, handle = 0, size = 0, version = 0;
            const int translated = open_flags_to_file(action.flags, flags);
            if (translated != 0) { return translated; }
            const auto result = file_client.open(path, flags, handle, size, version);
            if (result < 0) { return error_from_file(result); }
            open[index] = open_object{};
            open[index].kind = object_kind::file;
            open[index].handle = handle;
            open[index].flags = static_cast<u32>(action.flags);
            assign(action.first, index, (action.flags & O_CLOEXEC) != 0);
            return 0;
        }
        bool valid(int fd) { return fd >= 0 && fd < fd_count && fds[fd].object >= 0; }
    } snapshot;
    if (path == nullptr || argv == nullptr) { return EINVAL; }
    char working_directory[max_path];
    { runtime_guard guard(cwd_lock); memcpy(working_directory, current_directory, max_path); }
    char normalized_path[max_path];
    if (!normalize_path(path, normalized_path)) { return ENAMETOOLONG; }
    if (attributes != nullptr && *attributes != nullptr &&
        reinterpret_cast<const __posix_spawnattr*>(*attributes)->flags != 0) { return ENOTSUP; }
    action_set* set = nullptr;
    int error = spawn_action_set(actions, set);
    if (error != 0) { return error; }
    xos::sdk::spawn_options options{};
    options.delegate_spawn_depth = delegate_spawn_depth;
    options.working_directory = working_directory;
    char environment_bytes[16384];
    const char* environment_vector[xos::startup_environment_max + 1]{};
    u32 env_count = 0, environment_used = 0;
    {
        // setenv/unsetenv use newlib's environment lock. Snapshot copied bytes
        // before dropping it so loader RPC never borrows mutable env storage.
        struct environment_guard {
            bool active;
            explicit environment_guard(bool value) : active(value) {
#ifdef XOS_THREADED_RUNTIME
                if (active) { __env_lock(_REENT); }
#endif
            }
            ~environment_guard() {
#ifdef XOS_THREADED_RUNTIME
                if (active) { __env_unlock(_REENT); }
#endif
            }
        } guard(envp == nullptr);
        char* const* source = envp == nullptr ? environ : envp;
        if (source != nullptr) {
            while (source[env_count] != nullptr) {
                if (env_count == xos::startup_environment_max) { return E2BIG; }
                char checked[xos::process_max_arg_bytes];
                if (!copy_argument(source[env_count], checked, sizeof(checked))) { return E2BIG; }
                const u32 length = static_cast<u32>(strlen(checked) + 1);
                if (length > sizeof(environment_bytes) - environment_used) { return E2BIG; }
                memcpy(environment_bytes + environment_used, checked, length);
                environment_vector[env_count++] = environment_bytes + environment_used;
                environment_used += length;
            }
        }
    }
    options.environment = environment_vector;
    options.environment_count = env_count;
    // Ordered actions modify only the private snapshot, never live process FDs.
    if (set != nullptr) {
        for (u32 i = 0; i < set->count; ++i) {
            const spawn_action& action = set->actions[i];
            if (action.kind == action_kind::open) {
                const int error = snapshot.open_action(action);
                if (error != 0) { return error; }
            } else if (action.kind == action_kind::close) {
                if (!snapshot.valid(action.first)) { return EBADF; }
                snapshot.assign(action.first, -1);
            } else {
                if (!snapshot.valid(action.first)) { return EBADF; }
                snapshot.assign(action.second, snapshot.fds[action.first].object);
            }
        }
    }
    for (int fd = 0; fd < 3; ++fd) {
        if (!snapshot.valid(fd) || snapshot.fds[fd].close_on_exec) {
            options.stdio[fd] = -2;
            continue;
        }
        const open_object& object = snapshot.open[snapshot.fds[fd].object];
        if (object.kind == object_kind::kernel && object.stdio_source >= 0 && object.stdio_source < 3) {
            options.stdio[fd] = object.stdio_source;
        } else if (object.kind == object_kind::pipe_read || object.kind == object_kind::pipe_write) {
            options.stdio[fd] = object.handle;
        } else if (object.kind == object_kind::file) {
            options.file_handles[fd] = object.handle;
            options.open_flags[fd] = object.flags & ~O_CLOEXEC;
        } else { return ENOTSUP; }
    }
    u32 argc = 0;
    u32 aggregate = 0;
    while (argv[argc] != nullptr && argc < xos::process_max_args) {
        char checked[xos::process_max_arg_bytes];
        if (!copy_argument(argv[argc], checked, sizeof(checked))) { return E2BIG; }
        const u32 length = static_cast<u32>(strlen(checked) + 1);
        if (aggregate > 16384u - length) { return E2BIG; }
        aggregate += length;
        ++argc;
    }
    if (argv[argc] != nullptr) { return E2BIG; }
    if (options.environment != nullptr) {
        for (u32 i = 0; i < env_count; ++i) {
            char checked[xos::process_max_arg_bytes];
            if (!copy_argument(options.environment[i], checked, sizeof(checked))) { return E2BIG; }
            const u32 length = static_cast<u32>(strlen(checked) + 1);
            if (aggregate > 16384u - length) { return E2BIG; }
            aggregate += length;
        }
    }
    const xos::i64 child = xos::sdk::spawn_file_options(normalized_path, argc,
        const_cast<const char* const*>(argv), options);
    if (child < 0) {
        if (child == -8) { return E2BIG; }
        return error_from_spawn(child);
    }
    if (output_pid != nullptr) { *output_pid = static_cast<pid_t>(child); }
    return 0;
}

extern "C" int posix_spawn(pid_t* output_pid, const char* path,
                             const posix_spawn_file_actions_t* actions,
                             const posix_spawnattr_t* attributes,
                             char* const argv[], char* const envp[]) {
    return posix_spawn_with_depth(output_pid, path, actions, attributes, argv, envp, 0);
}

extern "C" int xos_posix_spawn_driver(pid_t* output_pid, const char* path,
                                        const posix_spawn_file_actions_t* actions,
                                        const posix_spawnattr_t* attributes,
                                        char* const argv[], char* const envp[]) {
    return posix_spawn_with_depth(output_pid, path, actions, attributes, argv, envp, 1);
}

extern "C" int posix_spawnp(pid_t* output_pid, const char* path,
                              const posix_spawn_file_actions_t* actions,
                              const posix_spawnattr_t* attributes,
                              char* const argv[], char* const envp[]) {
    if (path == nullptr) { return EINVAL; }
    for (u32 i = 0; path[i] != '\0'; ++i) {
        if (path[i] == '/') { return posix_spawn(output_pid, path, actions, attributes, argv, envp); }
    }
    const char* path_value = nullptr;
    char* const* environment = envp == nullptr ? environ : envp;
    if (environment != nullptr) {
        for (u32 i = 0; environment[i] != nullptr; ++i) {
            if (strncmp(environment[i], "PATH=", 5) == 0) { path_value = environment[i] + 5; break; }
        }
    }
    if (path_value == nullptr) { path_value = "/bin:/usr/bin"; }
    u32 start = 0;
    int last_error = ENOENT;
    while (true) {
        u32 end = start;
        while (path_value[end] != '\0' && path_value[end] != ':') { ++end; }
        char candidate[max_path];
        u32 used = 0;
        const u32 component_length = end - start;
        if (component_length >= max_path) {
            last_error = ENAMETOOLONG;
            if (path_value[end] == '\0') { break; }
            start = end + 1;
            continue;
        }
        if (end == start) {
            candidate[used++] = '.';
        } else {
            for (u32 i = start; i < end; ++i) { candidate[used++] = path_value[i]; }
        }
        if (used + 1 + strlen(path) < max_path) {
            if (candidate[used - 1] != '/') { candidate[used++] = '/'; }
            for (u32 i = 0; path[i] != '\0'; ++i) { candidate[used++] = path[i]; }
            candidate[used] = '\0';
            struct stat status{};
            if (stat(candidate, &status) == 0 && S_ISREG(status.st_mode)) {
                const int result = posix_spawn(output_pid, candidate, actions, attributes, argv, envp);
                if (result == 0) { return 0; }
                last_error = result;
            }
        }
        if (path_value[end] == '\0') { break; }
        start = end + 1;
    }
    return last_error;
}

extern "C" pid_t waitpid(pid_t pid, int* status, int options) {
    if (pid <= 0) { errno = EINVAL; return -1; }
    if ((options & ~WNOHANG) != 0) {
        errno = ENOTSUP;
        return -1;
    }
    xos::process_status result{};
    const xos::i64 waited = xos::sdk::syscall(xos::sys_process_wait,
        static_cast<xos::u64>(pid), reinterpret_cast<u64>(&result), (options & WNOHANG) ? 1 : 0);
    if (waited == xos::process_error_would_block && (options & WNOHANG)) { return 0; }
    if (waited < 0) { errno = error_from_kernel(waited); return -1; }
    if (status != nullptr) {
        if (result.outcome == xos::process_outcome::exited) { *status = (static_cast<int>(result.code) & 0xff) << 8; }
        else { *status = SIGKILL & 0x7f; }
    }
    return static_cast<pid_t>(result.pid);
}

extern "C" int fork(void) {
#ifdef XOS_THREADED_RUNTIME
    // No pthread-atfork or inherited-lock repair is provided by this profile.
    errno = ENOTSUP; return -1;
#else
    if (!runtime_ready) { errno = EIO; return -1; }
    const auto child = xos::sdk::syscall(xos::sys_process_fork_prepare);
    if (child == 0) { return 0; }
    if (child < 0) { errno = error_from_kernel(child); return -1; }
    xos::i64 cloned = static_cast<xos::i64>(xos::file::status::would_block);
    for (unsigned attempt = 0; attempt < 128 &&
         cloned == static_cast<xos::i64>(xos::file::status::would_block); ++attempt) {
        cloned = file_client.clone_session(static_cast<u64>(child));
        if (cloned == static_cast<xos::i64>(xos::file::status::would_block)) xos::sdk::yield();
    }
    const auto committed = cloned == 0 ? xos::sdk::syscall(xos::sys_process_fork_commit,
        static_cast<u64>(child)) : cloned;
    if (cloned != 0 || committed < 0) {
        (void)xos::sdk::syscall(xos::sys_process_abort, static_cast<u64>(child));
        errno = cloned != 0 ? error_from_file(cloned) : error_from_kernel(committed);
        return -1;
    }
    return static_cast<int>(child);
#endif
}
static int exec_image(const char* path, char* const argv[], char* const envp[], u32 depth_mode) {
#ifdef XOS_THREADED_RUNTIME
    (void)path; (void)argv; (void)envp; (void)depth_mode;
    errno = ENOTSUP; return -1;
#else
    if (!runtime_ready || !path || !argv) { errno = EINVAL; return -1; }
    char normalized[max_path], cwd[max_path];
    if (!normalize_path(path, normalized)) { errno = ENAMETOOLONG; return -1; }
    { runtime_guard guard(cwd_lock); memcpy(cwd, current_directory, max_path); }
    xos::sdk::spawn_options options{};
    options.replace_image = true; options.exec_depth_mode = depth_mode;
    options.working_directory = cwd;
    u32 argc = 0;
    char checked[xos::process_max_exec_arg_bytes];
    while (argc < xos::process_max_args && argv[argc]) {
        if (!copy_argument(argv[argc], checked, sizeof(checked))) { errno = E2BIG; return -1; }
        ++argc;
    }
    if (!argc || argv[argc]) { errno = E2BIG; return -1; }
    u32 env_count = 0;
    if (envp) while (env_count < xos::startup_environment_max && envp[env_count]) {
        if (!copy_argument(envp[env_count], checked, sizeof(checked))) { errno = E2BIG; return -1; }
        ++env_count;
    }
    if (envp && envp[env_count]) { errno = E2BIG; return -1; }
    options.environment_count = env_count; options.environment = const_cast<const char* const*>(envp);
    xos::startup_descriptor entries[fd_count]{};
    u32 count = 0;
    bool kept[object_count]{};
    {
        runtime_guard guard(fd_table_lock);
        for (u32 fd = 0; fd < fd_count; ++fd) {
            if (!valid_fd(static_cast<int>(fd)) || descriptors[fd].close_on_exec) continue;
            const auto index = static_cast<u32>(descriptors[fd].object);
            const auto& object = objects[index]; kept[index] = true;
            entries[count++] = {fd, index, static_cast<u32>(object.kind), object.handle, object.flags & ~O_CLOEXEC, 0};
        }
        for (u32 index = 0; index < object_count; ++index) {
            const auto& object = objects[index];
            if (object.kind == object_kind::none || kept[index]) continue;
            if (count == fd_count) { errno = EMFILE; return -1; }
            entries[count++] = {0xffffffffu, index, static_cast<u32>(object.kind), object.handle, object.flags & ~O_CLOEXEC, 0};
        }
    }
    options.descriptor_count = count; options.descriptors = entries;
    xos::execution::launch_diagnostic diagnostic{};
    const auto result = xos::execution::spawn_file_diagnosed(normalized, argc,
        const_cast<const char* const*>(argv), options, diagnostic);
    if (result >= 0) { errno = EIO; return -1; } // successful exec never returns
    using stage = xos::execution::launch_stage;
    if (diagnostic.stage == stage::open) errno = error_from_file(result);
    else if (diagnostic.stage == stage::inspect) errno = result == xos::thread_error_unsupported ? ENOTSUP : ENOEXEC;
    else if (diagnostic.stage == stage::prepare) errno = E2BIG;
    else errno = error_from_kernel(result);
    return -1;
#endif
}
extern "C" int execve(const char* path, char* const argv[], char* const envp[]) {
    return exec_image(path, argv, envp, 0);
}
extern "C" int _execve(const char* path, char* const argv[], char* const envp[]) { return execve(path, argv, envp); }
extern "C" int execv(const char* path, char* const argv[]) { return execve(path, argv, environ); }
extern "C" int xos_execve_driver(const char* path, char* const argv[], char* const envp[]) {
    return exec_image(path, argv, envp, 2); // require/decrease to GNU depth one
}
extern "C" int xos_execve_make(const char* path, char* const argv[], char* const envp[]) {
    return exec_image(path, argv, envp, 3); // require/decrease to Make depth two
}
extern "C" int xos_posix_spawn_make(pid_t* pid, const char* path,
    const posix_spawn_file_actions_t* actions, const posix_spawnattr_t* attributes,
    char* const argv[], char* const envp[]) {
    return posix_spawn_with_depth(pid, path, actions, attributes, argv, envp, 2);
}
extern "C" int execvp(const char* path, char* const argv[]) {
    if (!path || !*path) { errno = ENOENT; return -1; }
    if (strchr(path, '/')) return execve(path, argv, environ);
    const char* search = getenv("PATH"); if (!search) search = "/usr/bin:/bin";
    int saved = ENOENT;
    const size_t name_length = strlen(path);
    for (u32 start = 0;;) {
        u32 end = start; while (search[end] && search[end] != ':') ++end;
        const size_t directory_length = end - start;
        if (directory_length + (directory_length ? 1u : 0u) + name_length >= max_path) {
            saved = ENAMETOOLONG;
        } else {
            char candidate[max_path]; u32 used = 0;
            for (u32 i = start; i < end; ++i) candidate[used++] = search[i];
            if (end > start) candidate[used++] = '/';
            for (size_t i = 0; i < name_length; ++i) candidate[used++] = path[i];
            candidate[used] = 0;
            execve(candidate, argv, environ);
            if (errno != ENOENT && errno != ENOTDIR && errno != EACCES) return -1;
            if (errno == EACCES) saved = errno;
        }
        if (!search[end]) break;
        start = end + 1;
    }
    errno = saved; return -1;
}
extern "C" int xos_seal_anonymous(int fd) {
    object_lease lease(fd);
    if (lease.index < 0) { errno = EBADF; return -1; }
    auto& object = objects[lease.index];
    if (object.kind != object_kind::file) { errno = EINVAL; return -1; }
    const auto result = file_client.seal_anonymous(object.handle);
    if (result < 0) { errno = error_from_file(result); return -1; }
    { runtime_guard guard(fd_table_lock); object.flags = (object.flags & ~O_ACCMODE) | O_RDONLY; }
    return 0;
}
extern "C" int xos_open_anonymous(void) {
    u32 handle = 0;
    const auto result = file_client.anonymous(handle);
    if (result < 0) { errno = error_from_file(result); return -1; }
    if (!handle) { errno = EIO; return -1; }
    int object, fd;
    {
        runtime_guard guard(fd_table_lock);
        fd = alloc_fd(); object = fd < 0 ? -1 : alloc_object(object_kind::file, handle, O_RDWR);
        if (object >= 0) descriptors[fd] = {static_cast<signed char>(object), true};
    }
    if (object < 0) { (void)file_client.close(handle); errno = EMFILE; return -1; }
    return fd;
}
extern "C" int vfork(void) { errno = ENOSYS; return -1; }
extern "C" void* mmap(void*, size_t, int, int, int, off_t) { errno = ENOSYS; return reinterpret_cast<void*>(-1); }
extern "C" int munmap(void*, size_t) { errno = ENOSYS; return -1; }

extern "C" _READ_WRITE_RETURN_TYPE _write(int fd, const void* data, size_t length) {
    if (length > static_cast<size_t>(INT_MAX)) { length = static_cast<size_t>(INT_MAX); }
    size_t done = 0;
    while (done < length) {
        const _READ_WRITE_RETURN_TYPE result = write(fd, static_cast<const u8*>(data) + done,
                                     length - done);
        if (result < 0) { return done == 0 ? -1 : static_cast<_READ_WRITE_RETURN_TYPE>(done); }
        if (result == 0) { errno = EIO; return done == 0 ? -1 : static_cast<_READ_WRITE_RETURN_TYPE>(done); }
        done += static_cast<size_t>(result);
    }
    return static_cast<_READ_WRITE_RETURN_TYPE>(done);
}
extern "C" _READ_WRITE_RETURN_TYPE _read(int fd, void* data, size_t length) {
    if (length > static_cast<size_t>(INT_MAX)) { length = static_cast<size_t>(INT_MAX); }
    return read(fd, data, length);
}
extern "C" int _close(int fd) { return close(fd); }
extern "C" int _fstat(int fd, struct stat* status) { return fstat(fd, status); }
extern "C" int _stat(const char* path, struct stat* status) { return stat(path, status); }
extern "C" int _isatty(int fd) { return isatty(fd); }
extern "C" off_t _lseek(int fd, off_t offset, int whence) {
    const off_t result = lseek(fd, offset, whence);
    return result;
}
extern "C" [[noreturn]] void _exit(int code) {
    close_runtime_descriptors();
    xos::sdk::exit(code);
}
extern "C" int _getpid() { return static_cast<int>(xos::sdk::pid()); }
extern "C" int _kill(int, int) { errno = ENOSYS; return -1; }
extern "C" clock_t _times(struct tms*) { errno = ENOSYS; return static_cast<clock_t>(-1); }
extern "C" int getpid() { return _getpid(); }
extern "C" int kill(int pid, int sig) { return _kill(pid, sig); }
