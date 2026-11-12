// SPDX-License-Identifier: Apache-2.0
// XOS guest probe: public libc/SDK interfaces, no service or FatFs internals.
#include <xos/file_client.hpp>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
int failures;
void check(bool value, const char* label) {
    if (!value) { fprintf(stderr, "[file identity] FAILED %s errno=%d\n", label, errno); ++failures; }
}
void put(const char* path, const char* text) {
    const int fd = open(path, O_CREAT | O_TRUNC | O_RDWR, 0666);
    check(fd >= 0, "create file");
    if (fd < 0) { return; }
    check(write(fd, text, strlen(text)) == static_cast<ssize_t>(strlen(text)), "write file");
    check(close(fd) == 0, "close created file");
}
bool current(const char* expected) {
    char path[256];
    return getcwd(path, sizeof(path)) != nullptr && strcmp(path, expected) == 0;
}
bool contents(int fd, const char* text) {
    char bytes[32]{};
    const size_t length = strlen(text);
    return lseek(fd, 0, SEEK_SET) == 0 && read(fd, bytes, length) == static_cast<ssize_t>(length) &&
           memcmp(bytes, text, length) == 0;
}
int near_full() {
    const int fd = open("/nearfull.bin", O_RDWR);
    check(fd >= 0, "near-full existing file");
    if (fd < 0) { return 1; }
    struct stat before{}, after{};
    check(fstat(fd, &before) == 0 && before.st_size == 4, "near-full seed size");
    check(lseek(fd, 16384, SEEK_SET) == 16384, "near-full logical offset");
    errno = 0;
    check(ftruncate(fd, 16384) < 0 && errno == ENOSPC, "real near-full ftruncate fails");
    check(fstat(fd, &after) == 0 && after.st_size == 4 && lseek(fd, 0, SEEK_CUR) == 16384,
          "near-full truncate preserves length and offset");
    errno = 0;
    check(write(fd, "x", 1) < 0 && errno == ENOSPC, "real near-full hole write fails");
    check(fstat(fd, &after) == 0 && after.st_size == 4 && lseek(fd, 0, SEEK_CUR) == 16384 && contents(fd, "keep"),
          "near-full hole rollback preserves original bytes");
    xos::file::client files;
    check(files.init(), "near-full SDK client");
    check(files.begin_replace("/nearfull.bin", 1) == static_cast<xos::i64>(xos::file::status::no_space),
          "near-full atomic save reserves journal space");
    check(ftruncate(fd, 4094) == 0, "extend within allocated FAT16 cluster");
    const int filler = open("/filler.bin", O_WRONLY | O_APPEND);
    check(filler >= 0, "open prepared filler");
    if (filler >= 0) {
        char zero[4096]{};
        check(write(filler, zero, sizeof(zero)) == static_cast<ssize_t>(sizeof(zero)), "consume final real cluster");
        check(close(filler) == 0, "close full filler");
    }
    check(lseek(fd, 4094, SEEK_SET) == 4094 && write(fd, "abcdefgh", 8) == 2,
          "full disk returns actual partial write");
    errno = 0;
    check(write(fd, "z", 1) < 0 && errno == ENOSPC, "full disk zero progress reports error");
    check(rename("/replace_new", "/replace_old") < 0, "full disk rename journal cannot allocate");
    const int old = open("/replace_old", O_RDONLY);
    const int source = open("/replace_new", O_RDONLY);
    check(old >= 0 && source >= 0 && contents(old, "old") && contents(source, "new"),
          "full disk failed rename preserves source and target");
    if (old >= 0) { close(old); }
    if (source >= 0) { close(source); }
    check(unlink("/filler.bin") == 0, "release filler allocation");
    check(files.replace("/nearfull.bin", "recovered", 9) == 0 &&
          fstat(fd, &after) == 0 && after.st_nlink == 0 && after.st_size == 4096,
          "save recovers after space release and retains old fd");
    check(close(fd) == 0 && files.sync() == 0, "near-full final close and sync");
    if (failures == 0) { puts("FILE_IDENTITY_NEAR_FULL_OK"); }
    return failures == 0 ? 0 : 1;
}
int normal(const char* executable) {
    check(mkdir("/identity", 0777) == 0 && mkdir("/identity/parent", 0777) == 0, "identity directories");
    put("/identity/data", "abcdef");
    const int first = open("/identity/data", O_RDWR);
    const int second = open("/identity/data", O_RDWR);
    struct stat a{}, b{};
    check(first >= 0 && second >= 0 && fstat(first, &a) == 0 && fstat(second, &b) == 0 && a.st_ino == b.st_ino,
          "two writable opens share inode");
    check(write(first, "X", 1) == 1 && lseek(second, 0, SEEK_CUR) == 0 && contents(second, "Xbcdef"),
          "independent offsets coherent bytes");
    check(rename("/identity/data", "/identity/renamed") == 0 && stat("/identity/renamed", &b) == 0 && b.st_ino == a.st_ino,
          "rename retains open inode");
    check(unlink("/identity/renamed") == 0 && fstat(first, &b) == 0 && b.st_nlink == 0, "unlink retains open inode");
    put("/identity/renamed", "new");
    check(stat("/identity/renamed", &b) == 0 && b.st_ino != a.st_ino && contents(second, "Xbcdef"), "recreated path is a different file");
    check(close(first) == 0 && close(second) == 0, "independent closes");

    check(chdir("/identity/parent") == 0 && rename("/identity/parent", "/identity/moved") == 0,
          "rename active cwd");
    check(mkdir("/identity/parent", 0777) == 0 && current("/identity/moved"), "old cwd name reused without hijack");
    put("relative", "right");
    check(stat("/identity/moved/relative", &a) == 0 && stat("/identity/parent/relative", &b) < 0, "relative file stays in cwd object");
    DIR* stream = opendir(".");
    check(stream != nullptr, "open directory object");
    check(rename("/identity/moved", "/identity/final") == 0 && mkdir("/identity/moved", 0777) == 0,
          "rename directory with stream and cwd");
    bool saw_relative = false;
    if (stream != nullptr) {
        struct dirent* entry;
        while ((entry = readdir(stream)) != nullptr) { saw_relative = saw_relative || strcmp(entry->d_name, "relative") == 0; }
        check(saw_relative && chdir("/") == 0 && fchdir(dirfd(stream)) == 0 && current("/identity/final"),
              "directory stream and fchdir preserve identity");
        check(closedir(stream) == 0, "directory stream close");
    }
    check(mkdir("/identity/empty", 0777) == 0 && mkdir("/identity/source", 0777) == 0, "directory replacement setup");
    put("/identity/source/child", "keep");
    check(chdir("/identity/empty") == 0 && rename("/identity/source", "/identity/empty") == 0, "directory replaces empty active cwd");
    char path[256];
    errno = 0;
    check(getcwd(path, sizeof(path)) == nullptr && errno == ENOENT, "replaced cwd is detached");
    errno = 0;
    const int unexpected = open("new_child", O_CREAT | O_WRONLY, 0666);
    check(unexpected < 0 && errno == ENOENT, "replaced cwd cannot enter replacement");
    if (unexpected >= 0) { close(unexpected); }
    check(chdir("..") == 0 && current("/identity"), "detached cwd retains parent");
    check(stat("/identity/empty/child", &a) == 0, "replacement subtree intact");

    check(chdir("/identity/final") == 0, "cwd before fork");
    const int inherited = open("relative", O_RDONLY);
    int ready[2];
    if (inherited < 0 || pipe(ready) != 0) {
        check(false, "fork references setup");
        if (inherited >= 0) { close(inherited); }
        return 1;
    }
    const pid_t child = fork();
    check(child >= 0, "fork cwd and file references");
    if (child == 0) {
        close(ready[1]);
        char byte = 0;
        const bool valid = read(ready[0], &byte, 1) == 1 && current("/identity/fork_moved") &&
                           read(inherited, &byte, 1) == 1 && byte == 'r';
        _exit(valid ? 0 : 31);
    }
    if (child > 0) {
        close(ready[0]);
        check(rename("/identity/final", "/identity/fork_moved") == 0 && write(ready[1], "x", 1) == 1,
              "rename inherited cwd before child read");
        close(ready[1]);
        int result = 0;
        check(waitpid(child, &result, 0) == child && result == 0 && lseek(inherited, 0, SEEK_CUR) == 1,
              "fork shares offset and follows directory identity");
    }
    close(inherited);
    char* child_args[] = {const_cast<char*>(executable), const_cast<char*>("cwd_child"),
                         const_cast<char*>("/identity/fork_moved"), nullptr};
    pid_t spawned = 0;
    const int spawned_error = posix_spawn(&spawned, executable, nullptr, nullptr, child_args, nullptr);
    check(spawned_error == 0, "spawn inherits cwd reference");
    if (spawned_error == 0) {
        int result = 0;
        check(waitpid(spawned, &result, 0) == spawned && result == 0, "spawned cwd matches");
    }
    const pid_t executing = fork();
    check(executing >= 0, "fork before exec cwd check");
    if (executing == 0) { execv(executable, child_args); _exit(32); }
    if (executing > 0) {
        int result = 0;
        check(waitpid(executing, &result, 0) == executing && result == 0, "same-PID exec preserves cwd reference");
    }
    check(chdir("/") == 0, "release final cwd");
    if (failures == 0) { puts("FILE_IDENTITY_GUEST_OK"); }
    return failures == 0 ? 0 : 1;
}
}

int main(int argc, char** argv) {
    if (argc == 3 && strcmp(argv[1], "cwd_child") == 0) { return current(argv[2]) ? 0 : 33; }
    if (argc == 2 && strcmp(argv[1], "near_full") == 0) { return near_full(); }
    if (argc == 2 && strcmp(argv[1], "run") == 0) { return normal(argv[0]); }
    return 2;
}
