// SPDX-License-Identifier: Apache-2.0
#include <xos/sdk.hpp>
#include <xos/file_abi.hpp>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

extern "C" int audit_xos_libc_init(const xos::startup_info*);
extern "C" void audit_xos_libc_finish();
extern "C" int audit_open(const char*, int, ...);
extern "C" int audit_close(int);
extern "C" int audit_fcntl(int, int, ...);
extern "C" int audit_read(int, void*, size_t);
extern "C" int audit_write(int, const void*, size_t);
extern "C" int audit_stat(const char*, struct stat*);
extern "C" int audit_fstat(int, struct stat*);
extern "C" off_t audit_lseek(int, off_t, int);
extern "C" int audit_mkdir(const char*, mode_t);
extern "C" int audit_rename(const char*, const char*);
extern "C" int audit_unlink(const char*);
extern "C" int audit_rmdir(const char*);
extern "C" int audit_chdir(const char*);
extern "C" int audit_fchdir(int);
extern "C" char* audit_getcwd(char*, size_t);
extern "C" DIR* audit_opendir(const char*);
extern "C" struct dirent* audit_readdir(DIR*);
extern "C" int audit_closedir(DIR*);
extern "C" int audit_dirfd(DIR*);
extern "C" void identity_service_mount(const char*);
extern "C" void identity_service_request(const xos::file::request*, xos::file::response*);
extern "C" void identity_service_finished();

namespace {
int saved_errno;
unsigned cases;
xos::file::response response;
void require(bool value, const char* label) {
    if (!value) { printf("FAIL %s errno=%d\n", label, saved_errno); exit(1); }
}
void checked(const char* label) { ++cases; printf("[libc identity] %s ok\n", label); }
void create(const char* name, const char* value) {
    const int fd = audit_open(name, O_CREAT | O_RDWR | O_TRUNC, 0666);
    require(fd >= 0, "create open");
    require(audit_write(fd, value, strlen(value)) == static_cast<int>(strlen(value)), "create write");
    require(audit_close(fd) == 0, "create close");
}
void expect_cwd(const char* expected) {
    char path[256];
    require(audit_getcwd(path, sizeof(path)) == path && strcmp(path, expected) == 0, "getcwd identity");
}
bool listed(DIR* directory, const char* name) {
    struct dirent* entry;
    while ((entry = audit_readdir(directory)) != nullptr) {
        if (strcmp(entry->d_name, name) == 0) { return true; }
    }
    return false;
}
}

extern "C" int* __errno() { return &saved_errno; }
namespace xos::sdk {
u16 target_elf_machine() { return 62; }
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    if (number == 6) { return 10; }
    if (number == sys_ipc_handles) {
        auto* handles = reinterpret_cast<u32*>(first);
        handles[0] = 100; handles[1] = 101;
        return 0;
    }
    if (number == 4) {
        if (first != 100 || third != sizeof(file::request)) { return -1; }
        identity_service_request(reinterpret_cast<const file::request*>(second), &response);
        return 0;
    }
    if (number == 5) {
        if (first != 101 || third != sizeof(response)) { return -1; }
        memcpy(reinterpret_cast<void*>(second), &response, sizeof(response));
        return sizeof(response);
    }
    if (number == sys_process_guard || number == sys_handle_close || number == 3) { return 0; }
    return process_error_invalid;
}
}

int main(int argc, char** argv) {
    require(argc == 2, "private image argument");
    identity_service_mount(argv[1]);
    alignas(16) unsigned char page[4096]{};
    auto* startup = reinterpret_cast<xos::startup_info*>(page);
    startup->version = 2; startup->reserved = xos::startup_extension_offset;
    auto* extension = reinterpret_cast<xos::startup_extension*>(page + startup->reserved);
    extension->magic = xos::startup_extension_magic;
    extension->flags = 7; // no console routes in this IPC-only host fixture
    extension->working_directory = reinterpret_cast<xos::u64>("/");
    require(audit_xos_libc_init(startup) == 0, "real libc initializes cwd through service");
    expect_cwd("/");
    checked("startup_cwd_protocol");

    create("/data", "abc");
    const int writer = audit_open("/data", O_RDWR);
    const int reader = audit_open("/data", O_RDONLY);
    require(writer >= 0 && reader >= 0 && writer != reader, "independent libc open");
    struct stat a{}, b{};
    require(audit_fstat(writer, &a) == 0 && audit_fstat(reader, &b) == 0 && a.st_ino == b.st_ino,
            "libc shared inode");
    require(audit_write(writer, "X", 1) == 1 && audit_lseek(reader, 0, SEEK_CUR) == 0, "independent libc offset");
    char bytes[16]{};
    require(audit_read(reader, bytes, 3) == 3 && memcmp(bytes, "Xbc", 3) == 0, "libc shared content");
    checked("independent_open_real_stack");

    require(audit_unlink("/data") == 0 && audit_fstat(reader, &b) == 0 && b.st_nlink == 0 && b.st_ino == a.st_ino,
            "libc unlinked fstat identity and nlink");
    create("/data", "new");
    require(audit_stat("/data", &b) == 0 && b.st_ino != a.st_ino, "libc recreated inode distinct");
    require(audit_lseek(reader, 0, SEEK_SET) == 0 && audit_read(reader, bytes, 3) == 3 &&
            memcmp(bytes, "Xbc", 3) == 0, "libc old fd retained after recreation");
    require(audit_close(writer) == 0 && audit_close(reader) == 0, "libc unlink closes");
    checked("unlink_recreate_libc_identity");

    require(audit_mkdir("/parent", 0777) == 0 && audit_mkdir("/parent/child", 0777) == 0, "libc cwd setup");
    require(audit_chdir("/parent/child") == 0, "libc chdir");
    require(audit_rename("/parent", "/moved") == 0, "libc rename cwd ancestor");
    require(audit_mkdir("/parent", 0777) == 0 && audit_mkdir("/parent/child", 0777) == 0, "libc old path replacement");
    expect_cwd("/moved/child");
    create("relative", "right");
    require(audit_stat("/moved/child/relative", &a) == 0 && audit_stat("/parent/child/relative", &b) < 0 &&
            saved_errno == ENOENT, "libc relative request uses server cwd");
    checked("cwd_rename_and_relative_open");

    DIR* directory = audit_opendir(".");
    require(directory != nullptr, "libc opendir");
    const int directory_fd = audit_dirfd(directory);
    require(directory_fd >= 0 && audit_fcntl(directory_fd, F_GETFD) == FD_CLOEXEC, "directory fd closes on exec");
    require(audit_rename("/moved/child", "/moved/renamed") == 0 && audit_mkdir("/moved/child", 0777) == 0,
            "rename opened directory and recreate");
    create("/moved/child/wrong", "bad");
    require(listed(directory, "relative"), "readdir follows opened directory identity");
    require(!listed(directory, "wrong"), "readdir ignores recreated path");
    require(audit_chdir("/") == 0 && audit_fchdir(directory_fd) == 0, "fchdir actual directory handle");
    expect_cwd("/moved/renamed");
    require(audit_closedir(directory) == 0 && audit_fcntl(directory_fd, F_GETFD) < 0, "closedir releases underlying fd");
    checked("directory_stream_identity_and_fchdir");

    require(audit_mkdir("/empty", 0777) == 0 && audit_chdir("/empty") == 0, "deleted cwd setup");
    const int root_fd = audit_open("/", O_RDONLY | O_DIRECTORY);
    require(root_fd >= 0, "open directory root");
    require(audit_rmdir("/empty") == 0 && audit_mkdir("/empty", 0777) == 0, "rmdir cwd and replace name");
    char cwd_buffer[256];
    require(audit_getcwd(cwd_buffer, sizeof(cwd_buffer)) == nullptr && saved_errno == ENOENT, "deleted cwd getcwd fails");
    require(audit_open("new", O_CREAT | O_WRONLY, 0666) < 0 && saved_errno == ENOENT, "deleted cwd create cannot be hijacked");
    require(audit_fchdir(root_fd) == 0 && audit_close(root_fd) == 0, "fchdir escapes deleted cwd");
    expect_cwd("/");
    checked("deleted_cwd_errors_and_fchdir_recovery");

    require(audit_rmdir("/moved") < 0 && saved_errno == ENOTEMPTY, "non-empty directory errno");
    require(audit_stat("/missing/../data", &a) < 0 && saved_errno == ENOENT, "missing dotdot component");
    require(audit_stat("/data/../data", &a) < 0 && saved_errno == ENOTDIR, "file dotdot component");
    require(audit_open("/data", O_RDONLY | O_DIRECTORY) < 0 && saved_errno == ENOTDIR, "directory flag type error");
    require(audit_fchdir(31) < 0 && saved_errno == EBADF, "bad fchdir descriptor");
    checked("path_and_directory_errno_real_service");

    require(audit_chdir("/moved/renamed") == 0, "cwd before runtime reinitialization");
    audit_xos_libc_finish();
    // Same PID/retained file session models the new CRT's initialization after
    // exec. The old startup path must not overwrite the service's live cwd.
    require(audit_xos_libc_init(startup) == 0, "reinitialize runtime with old startup cwd");
    expect_cwd("/moved/renamed");
    char small[2];
    require(audit_getcwd(small, sizeof(small)) == nullptr && saved_errno == ERANGE, "getcwd small buffer");
    char* allocated = audit_getcwd(nullptr, 0);
    require(allocated != nullptr && strcmp(allocated, "/moved/renamed") == 0, "allocated getcwd");
    free(allocated);
    checked("runtime_reinitialization_preserves_session_cwd");

    audit_xos_libc_finish();
    identity_service_finished();
    checked("all_directory_and_file_references_reclaimed");
    printf("LIBC_FILE_IDENTITY_CASES_PASSED=%u\n", cases);
    return 0;
}
