// SPDX-License-Identifier: Apache-2.0
// Production libc and file client, with the kernel/file-service boundary
// substituted. The runner renames libc exports so they cannot interpose on
// the host process's own libc.
#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>
#include <errno.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern "C" int audit_xos_libc_init(const xos::startup_info*);
extern "C" int audit_close(int);
extern "C" int audit_fcntl(int, int, ...);
extern "C" int audit_write(int, const void*, size_t);
extern "C" int audit_read(int, void*, size_t);
extern "C" int audit_execvp(const char*, char* const[]);
extern "C" int audit_execve(const char*, char* const[], char* const[]);
extern "C" int audit_posix_spawn(pid_t*, const char*, const posix_spawn_file_actions_t*,
                                  const posix_spawnattr_t*, char* const[], char* const[]);

namespace {
int saved_errno;
unsigned opened_files, closed_files;
xos::file::response response;
bool active[16];
bool test_exec_paths;
unsigned exec_open_calls;
char exec_open_path[256];
bool test_spawn_errors;
int spawn_open_error, spawn_cwd_error;
xos::i64 spawn_create_result;
unsigned create_attempts, aborted_children, exec_prepares;
unsigned image_offset;
unsigned char spawn_image[512];
void image_integer(unsigned offset, xos::u64 value, unsigned bytes) {
    for (unsigned i = 0; i < bytes; ++i) { spawn_image[offset + i] = static_cast<unsigned char>(value >> (i * 8)); }
}
void valid_image() {
    memset(spawn_image, 0, sizeof(spawn_image));
    memcpy(spawn_image, "\x7f" "ELF", 4);
    spawn_image[4] = 2; spawn_image[5] = 1; spawn_image[6] = 1;
    image_integer(16, 2, 2); image_integer(18, 62, 2); image_integer(20, 1, 4);
    image_integer(24, 0x40000080, 8); image_integer(32, 64, 8);
    image_integer(52, 64, 2); image_integer(54, 56, 2); image_integer(56, 1, 2);
    image_integer(64, 1, 4); image_integer(68, 5, 4);
    image_integer(80, 0x40000000, 8); image_integer(96, sizeof(spawn_image), 8);
    image_integer(104, sizeof(spawn_image), 8); image_integer(112, 4096, 8);
    image_integer(40, 256, 8); image_integer(58, 64, 2);
    image_integer(60, 3, 2); image_integer(62, 1, 2);
    memcpy(spawn_image + 224, "\0.shstrtab\0.xos.exec", 21);
    image_integer(344, 224, 8); image_integer(352, 21, 8);
    image_integer(384, 11, 4); image_integer(388, 1, 4); image_integer(392, 2, 8);
    image_integer(400, 0x400000c0, 8); image_integer(408, 192, 8); image_integer(416, 16, 8);
    image_integer(192, xos::exec_image_abi_magic, 8);
    image_integer(200, 3, 4); image_integer(204, 16, 4);
}
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
            if (test_spawn_errors) {
                response.status_code = spawn_open_error;
                if (spawn_open_error == 0) {
                    response.handle = ++opened_files;
                    response.value = sizeof(spawn_image);
                    active[response.handle] = true;
                    image_offset = 0;
                }
            } else if (test_exec_paths) {
                ++exec_open_calls;
                memcpy(exec_open_path, request.name, sizeof(exec_open_path));
                response.status_code = static_cast<i32>(file::status::not_found);
            } else {
                response.handle = ++opened_files;
                active[response.handle] = true;
            }
        } else if (operation == file::op::cwd_set) {
            response.status_code = test_spawn_errors && request.offset != 0 ? spawn_cwd_error : 0;
        } else if (operation == file::op::seek && test_spawn_errors) {
            image_offset = static_cast<unsigned>(request.offset);
            response.value = image_offset;
        } else if (operation == file::op::stat && test_exec_paths) {
            response.flags = file::stat_is_directory;
        } else if (operation == file::op::close || operation == file::op::read ||
                   operation == file::op::write) {
            if (request.handle >= 16 || !active[request.handle]) {
                response.status_code = static_cast<i32>(file::status::bad_handle);
            } else if (operation == file::op::close) {
                ++closed_files; active[request.handle] = false;
            } else if (operation == file::op::read) {
                if (test_spawn_errors) {
                    const unsigned left = image_offset < sizeof(spawn_image) ? sizeof(spawn_image) - image_offset : 0;
                    response.length = request.length < left ? request.length : left;
                    memcpy(response.data, spawn_image + image_offset, response.length);
                    image_offset += response.length;
                } else {
                    response.length = request.length ? 1 : 0;
                    response.data[0] = 'x';
                }
                response.value = response.length;
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
    if (number == sys_process_create && test_spawn_errors) {
        ++create_attempts;
        return spawn_create_result;
    }
    if (number == sys_process_exec_prepare && test_spawn_errors) {
        ++exec_prepares;
        return process_error_resources;
    }
    if (number == sys_process_abort && test_spawn_errors) { ++aborted_children; return 0; }
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
        {"", "x", 1, ENOENT},
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
    test_exec_paths = false;
    test_spawn_errors = true;
    struct spawn_case { int open_error; xos::i64 create_result; int cwd_error; bool malformed; int expected; };
    const spawn_case failures[] = {
        {0, xos::process_error_denied, 0, false, EPERM},
        {0, xos::process_error_resources, 0, false, ENOMEM},
        {0, xos::process_error_busy, 0, false, EBUSY},
        {static_cast<int>(xos::file::status::not_found), 0, 0, false, ENOENT},
        {static_cast<int>(xos::file::status::busy), 0, 0, false, EBUSY},
        {static_cast<int>(xos::file::status::would_block), 0, 0, false, EAGAIN},
        {0, 0, 0, true, ENOEXEC},
        {0, 22, static_cast<int>(xos::file::status::not_found), false, ENOENT},
        {0, 22, static_cast<int>(xos::file::status::busy), false, EBUSY},
        {0, 22, static_cast<int>(xos::file::status::would_block), false, EAGAIN},
    };
    unsigned spawn_passed = 0;
    alignas(16) xos::startup_info initial{};
    initial.version = 1;
    initial.handles[0] = 0; initial.handles[1] = 1; initial.handles[2] = 2;
    if (!check(audit_xos_libc_init(&initial) == 0, "spawn test runtime startup")) return 1;
    for (const auto& test : failures) {
        valid_image();
        if (test.malformed) { spawn_image[0] = 0; }
        spawn_open_error = test.open_error; spawn_create_result = test.create_result;
        spawn_cwd_error = test.cwd_error;
        opened_files = closed_files = create_attempts = aborted_children = 0;
        memset(active, 0, sizeof(active));
        pid_t result_pid = 999;
        char* environment[] = {nullptr};
        const int result = audit_posix_spawn(&result_pid, "/probe", nullptr, nullptr, arguments, environment);
        const unsigned expected_create = test.open_error == 0 && !test.malformed ? 1 : 0;
        const bool valid = result == test.expected && result_pid == 999 &&
            create_attempts == expected_create && opened_files == closed_files &&
            aborted_children == static_cast<unsigned>(test.cwd_error != 0);
        printf("spawn error case %u: %s (result=%d, expected=%d, create=%u, abort=%u)\n",
               static_cast<unsigned>(&test - failures), valid ? "ok" : "FAIL", result,
               test.expected, create_attempts, aborted_children);
        if (valid) ++spawn_passed;
    }
    if (spawn_passed != sizeof(failures) / sizeof(failures[0])) return 1;
    printf("LIBC_SPAWN_ERROR_CASES_PASSED=%u\n", spawn_passed);
    valid_image();
    spawn_open_error = spawn_cwd_error = 0;
    opened_files = closed_files = exec_prepares = 0;
    char* environment[] = {nullptr};
    saved_errno = 0;
    const int executed = audit_execve("/probe", arguments, environment);
    if (!check(executed == -1 && saved_errno == ENOMEM && exec_prepares == 1 &&
               opened_files == closed_files, "exec inherited cwd reaches actual kernel prepare")) return 1;
    puts("LIBC_EXEC_CWD_CASES_PASSED=1");
    return 0;
}
