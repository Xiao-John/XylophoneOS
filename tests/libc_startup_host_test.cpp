// SPDX-License-Identifier: Apache-2.0
// Production libc and file client, with the kernel/file-service boundary
// substituted. The runner renames libc exports so they cannot interpose on
// the host process's own libc.
#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" int audit_xos_libc_init(const xos::startup_info*);
extern "C" int audit_close(int);
extern "C" int audit_fcntl(int, int, ...);
extern "C" int audit_write(int, const void*, size_t);
extern "C" int audit_read(int, void*, size_t);
extern "C" int audit_execvp(const char*, char* const[]);

namespace {
int saved_errno;
unsigned opened_files, closed_files;
xos::file::response response;
bool active[16];
bool test_exec_paths;
unsigned exec_open_calls;
char exec_open_path[256];
bool check(bool condition, const char* message) {
    if (!condition) printf("FAIL %s\n", message);
    return condition;
}
}

extern "C" int* __errno() { return &saved_errno; }

namespace xos::sdk {
u16 target_elf_machine() { return 62; }
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == 6) return 10;
    if (number == sys_ipc_handles) {
        auto* handles = reinterpret_cast<u32*>(first);
        handles[0] = 100; handles[1] = 101;
        return 0;
    }
    if (number == 4) {
        if (first != 100 || third != sizeof(file::request)) return -1;
        const auto& request = *reinterpret_cast<const file::request*>(second);
        response = {};
        response.magic = file::response_magic;
        response.version = file::abi_version;
        response.request_id = request.request_id;
        const auto operation = static_cast<file::op>(request.operation);
        if (operation == file::op::open) {
            if (test_exec_paths) {
                ++exec_open_calls;
                memcpy(exec_open_path, request.name, sizeof(exec_open_path));
                response.status_code = static_cast<i32>(file::status::not_found);
            } else {
                response.handle = ++opened_files;
                active[response.handle] = true;
            }
        } else if (operation == file::op::stat && test_exec_paths) {
            response.flags = file::stat_is_directory;
        } else if (operation == file::op::close || operation == file::op::read ||
                   operation == file::op::write) {
            if (request.handle >= 16 || !active[request.handle]) {
                response.status_code = static_cast<i32>(file::status::bad_handle);
            } else if (operation == file::op::close) {
                ++closed_files; active[request.handle] = false;
            } else if (operation == file::op::read) {
                response.length = request.length ? 1 : 0;
                response.value = response.length;
                response.data[0] = 'x';
            } else {
                response.value = request.length;
            }
        } else {
            response.status_code = static_cast<i32>(file::status::invalid);
        }
        return 0;
    }
    if (number == 5) {
        if (first != 101 || third != sizeof(response)) return -1;
        memcpy(reinterpret_cast<void*>(second), &response, sizeof(response));
        return sizeof(response);
    }
    if (number == sys_handle_close || number == 3) return 0;
    return process_error_invalid;
}
}

int main() {
    unsigned cases = 0;
    const unsigned closed_masks[] = {0, 1, 2, 4, 7};
    for (unsigned closed_mask : closed_masks) {
        for (unsigned target = 0; target < 3; ++target) {
            alignas(16) unsigned char page[4096]{};
            auto* startup = reinterpret_cast<xos::startup_info*>(page);
            startup->version = 2;
            startup->reserved = xos::startup_extension_offset;
            startup->handles[0] = 0; startup->handles[1] = 1; startup->handles[2] = 2;
            auto* extension = reinterpret_cast<xos::startup_extension*>(page + startup->reserved);
            extension->magic = xos::startup_extension_magic;
            extension->flags = closed_mask;
            extension->open_paths[target] = reinterpret_cast<xos::u64>("/redirect.txt");
            extension->open_flags[target] = target == 0 ? O_RDONLY : O_WRONLY;
            opened_files = closed_files = 0;
            memset(active, 0, sizeof(active));
            if (!check(audit_xos_libc_init(startup) == 0, "startup succeeds") ||
                !check(audit_fcntl(static_cast<int>(target), F_GETFD) == 0, "redirected descriptor remains open") ||
                !check(opened_files == 1 && closed_files == 0, "startup retains opened file")) return 1;
            char byte = 0;
            const int progress = target == 0 ? audit_read(0, &byte, 1) :
                audit_write(static_cast<int>(target), "x", 1);
            if (!check(progress == 1, "redirected I/O reaches file")) return 1;
            for (int fd = 0; fd < 3; ++fd) (void)audit_close(fd);
            if (!check(closed_files == 1, "redirected file closes exactly once")) return 1;
            ++cases;
        }
    }
    printf("LIBC_STARTUP_CASES_PASSED=%u\n", cases);

    test_exec_paths = true;
    char directory[256], trailing[256], boundary[256], too_long[256], search[264];
    directory[0] = '/';
    memset(directory + 1, 'a', 252);
    directory[253] = '\0';
    snprintf(trailing, sizeof(trailing), "%s/", directory);
    snprintf(boundary, sizeof(boundary), "%s/x", directory);
    too_long[0] = '/';
    memset(too_long + 1, 'a', 253);
    too_long[254] = '/'; too_long[255] = '\0';
    snprintf(search, sizeof(search), "%s:/bin", trailing);
    struct path_case { const char* search; const char* expected; unsigned opens; int error; };
    const path_case paths[] = {
        {"/bin/", "/bin/x", 1, ENOENT},
        {directory, boundary, 1, ENOENT},
        {trailing, boundary, 1, ENOENT},
        {too_long, "", 0, ENAMETOOLONG},
        {"", "/x", 1, ENOENT},
        {search, "/bin/x", 2, ENOENT},
    };
    char name[] = "x";
    char* arguments[] = {name, nullptr};
    unsigned passed = 0;
    for (const auto& test : paths) {
        if (!check(setenv("PATH", test.search, 1) == 0, "set host search path")) return 1;
        exec_open_calls = 0; exec_open_path[0] = '\0'; saved_errno = 0;
        const int result = audit_execvp(name, arguments);
        const bool valid = result == -1 && saved_errno == test.error &&
            exec_open_calls == test.opens && strcmp(exec_open_path, test.expected) == 0;
        printf("execvp path case %u: %s (opens=%u, errno=%d)\n",
               static_cast<unsigned>(&test - paths), valid ? "ok" : "FAIL",
               exec_open_calls, saved_errno);
        if (valid) ++passed;
    }
    if (passed != sizeof(paths) / sizeof(paths[0])) return 1;
    printf("LIBC_EXECVP_CASES_PASSED=%u\n", passed);
    return 0;
}
