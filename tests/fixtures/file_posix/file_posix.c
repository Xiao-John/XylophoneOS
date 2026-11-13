// SPDX-License-Identifier: Apache-2.0
// Guest acceptance for POSIX path resolution, file offsets and spawn actions.
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static int failures;

static void check(int condition, const char* stage) {
    if (condition) { return; }
    fprintf(stderr, "[posix] FAILED %s errno=%d\n", stage, errno);
    ++failures;
}

static int read_text(const char* path, char* buffer, size_t size) {
    const int fd = open(path, O_RDONLY);
    if (fd < 0) { return -1; }
    const ssize_t got = read(fd, buffer, size - 1);
    close(fd);
    if (got < 0) { return -1; }
    buffer[got] = '\0';
    return (int)got;
}

static void write_text(const char* path, const char* text) {
    const int fd = open(path, O_CREAT | O_TRUNC | O_WRONLY, 0644);
    if (fd < 0) { return; }
    (void)write(fd, text, strlen(text));
    close(fd);
}

static int spawn_with_actions(const char* path, const char* mode,
                              posix_spawn_file_actions_t* actions) {
    char* arguments[] = {(char*)path, (char*)mode, 0};
    pid_t child = 0;
    const int error = posix_spawn(&child, path, actions, 0, arguments, 0);
    if (error != 0) { errno = error; return -1; }
    int status = 0;
    if (waitpid(child, &status, 0) != child || status != 0) { return -1; }
    return 0;
}

int main(int argc, char** argv) {
    if (argc >= 2 && strcmp(argv[1], "emit") == 0) {
        (void)write(1, "CHILD\n", 6);
        return 0;
    }
    if (argc < 2 || strcmp(argv[1], "run") != 0) { return 2; }
    mkdir("/case", 0777);

    // Empty paths are not the current directory.
    errno = 0;
    check(stat("", &(struct stat){0}) != 0 && errno == ENOENT, "stat empty");
    errno = 0;
    check(chdir("") != 0 && errno == ENOENT, "chdir empty");

    // ".." must not hide a missing or non-directory intermediate component.
    errno = 0;
    check(stat("/case/missing/../x", &(struct stat){0}) != 0 && errno == ENOENT, "missing intermediate");
    write_text("/case/plain", "plain");
    errno = 0;
    check(stat("/case/plain/../x", &(struct stat){0}) != 0 && errno == ENOTDIR, "file intermediate");

    // A trailing slash requires a directory and must not delete a file.
    errno = 0;
    check(stat("/case/plain/", &(struct stat){0}) != 0 && errno == ENOTDIR, "stat trailing file");
    errno = 0;
    check(unlink("/case/plain/") != 0 && errno == ENOTDIR, "unlink trailing file");
    struct stat info = {0};
    check(stat("/case/plain", &info) == 0 && S_ISREG(info.st_mode), "file survived trailing unlink");
    errno = 0;
    check(open("/case/plain/", O_RDONLY) != 0 && errno == ENOTDIR, "open trailing file");
    mkdir("/case/dir", 0777);
    errno = 0;
    check(open("/case/dir/", O_RDONLY) != 0 && errno == EISDIR, "open trailing directory");

    // O_TRUNC/O_APPEND without O_CREAT do not create files.
    errno = 0;
    check(open("/case/absent", O_WRONLY | O_TRUNC) != 0 && errno == ENOENT, "truncate without create");
    errno = 0;
    check(open("/case/absent", O_WRONLY | O_APPEND) != 0 && errno == ENOENT, "append without create");
    check(stat("/case/absent", &info) != 0, "absent still absent");
    write_text("/case/existing", "abcdef");
    const int truncated = open("/case/existing", O_WRONLY | O_TRUNC);
    check(truncated >= 0, "truncate existing open");
    if (truncated >= 0) { close(truncated); }
    check(stat("/case/existing", &info) == 0 && info.st_size == 0, "truncate existing size");

    // ftruncate preserves the offset.
    write_text("/case/offset", "0123456789");
    const int offset_fd = open("/case/offset", O_RDWR);
    check(offset_fd >= 0, "offset open");
    if (offset_fd >= 0) {
        check(lseek(offset_fd, 2, SEEK_SET) == 2, "offset seek");
        check(ftruncate(offset_fd, 4) == 0, "offset truncate");
        check(lseek(offset_fd, 0, SEEK_CUR) == 2, "offset preserved");
        struct stat offset_info = {0};
        check(fstat(offset_fd, &offset_info) == 0 && offset_info.st_size == 4, "offset size");
        close(offset_fd);
    }

    // Growing ftruncate zero-fills.
    write_text("/case/grow", "ABCD");
    const int grow_fd = open("/case/grow", O_RDWR);
    check(grow_fd >= 0, "grow open");
    if (grow_fd >= 0) {
        check(ftruncate(grow_fd, 12) == 0, "grow truncate");
        check(lseek(grow_fd, 0, SEEK_SET) == 0, "grow rewind");
        char grown[13] = {0};
        check(read(grow_fd, grown, 12) == 12, "grow read");
        check(memcmp(grown, "ABCD\0\0\0\0\0\0\0\0", 12) == 0, "grow zeros");
        close(grow_fd);
    }

    // Seeking past EOF must not change the length.
    write_text("/case/hole", "xy");
    const int hole_fd = open("/case/hole", O_RDWR);
    check(hole_fd >= 0, "hole open");
    if (hole_fd >= 0) {
        check(lseek(hole_fd, 8, SEEK_SET) == 8, "hole seek");
        struct stat hole_info = {0};
        check(fstat(hole_fd, &hole_info) == 0 && hole_info.st_size == 2, "seek does not extend");
        check(write(hole_fd, "Z", 1) == 1, "hole write");
        close(hole_fd);
        char hole[10] = {0};
        check(read_text("/case/hole", hole, sizeof(hole)) == 9 &&
              memcmp(hole, "xy\0\0\0\0\0\0Z", 9) == 0, "hole zeros");
    }

    // rename replaces an existing file.
    write_text("/case/source", "new");
    write_text("/case/target", "old");
    check(rename("/case/source", "/case/target") == 0, "rename replace");
    char replaced[8] = {0};
    check(read_text("/case/target", replaced, sizeof(replaced)) == 3 &&
          memcmp(replaced, "new", 3) == 0, "rename content");
    check(stat("/case/source", &info) != 0, "rename source gone");

    // A directory cannot move into its own descendant.
    check(mkdir("/case/tree", 0777) == 0, "mkdir tree");
    check(mkdir("/case/tree/sub", 0777) == 0, "mkdir tree/sub");
    errno = 0;
    check(rename("/case/tree", "/case/tree/sub/moved") != 0, "reject descendant rename");
    struct stat tree_info = {0};
    check(stat("/case/tree", &tree_info) == 0 && S_ISDIR(tree_info.st_mode), "tree intact");
    check(stat("/case/tree/sub", &tree_info) == 0 && S_ISDIR(tree_info.st_mode), "subtree intact");

    // open reuses the lowest free descriptor.
    close(0);
    const int reused = open("/case/plain", O_RDONLY);
    check(reused == 0, "open reuses fd 0");
    if (reused >= 0) { close(reused); }

    // Spawn open actions use the working directory in effect at spawn time.
    mkdir("/case/s1", 0777);
    mkdir("/case/s2", 0777);
    check(chdir("/case/s1") == 0, "chdir s1");
    posix_spawn_file_actions_t relative;
    check(posix_spawn_file_actions_init(&relative) == 0, "actions init relative");
    check(posix_spawn_file_actions_addopen(&relative, 1, "out.txt",
                                           O_CREAT | O_TRUNC | O_WRONLY, 0644) == 0,
          "addopen relative");
    check(chdir("/case/s2") == 0, "chdir s2");
    check(spawn_with_actions("/bin/file_posix.elf", "emit", &relative) == 0,
          "spawn relative open");
    posix_spawn_file_actions_destroy(&relative);
    char output[16] = {0};
    check(read_text("/case/s2/out.txt", output, sizeof(output)) == 6 &&
          memcmp(output, "CHILD\n", 6) == 0, "spawn-time cwd open");
    check(stat("/case/s1/out.txt", &info) != 0, "registration cwd not used");

    // close then dup2 with the same descriptor must fail the spawn.
    const int extra = open("/case/extra", O_CREAT | O_RDWR, 0644);
    check(extra >= 0, "extra open");
    if (extra >= 0) {
        posix_spawn_file_actions_t ordered;
        check(posix_spawn_file_actions_init(&ordered) == 0, "actions init ordered");
        check(posix_spawn_file_actions_addclose(&ordered, extra) == 0, "addclose high fd");
        check(posix_spawn_file_actions_adddup2(&ordered, extra, 1) == 0, "adddup2 after close");
        pid_t child = 0;
        char* arguments[] = {(char*)"/bin/file_posix.elf", (char*)"emit", 0};
        errno = 0;
        const int error = posix_spawn(&child, "/bin/file_posix.elf", &ordered, 0,
                                      arguments, 0);
        check(error == EBADF, "spawn fails after close");
        if (error == 0) { (void)waitpid(child, nullptr, 0); }
        posix_spawn_file_actions_destroy(&ordered);
        close(extra);
    }

    // readdir yields the synthetic "." and ".." entries.
    DIR* dir = opendir("/case");
    check(dir != NULL, "readdir open");
    if (dir != NULL) {
        struct dirent* first = readdir(dir);
        char first_name[8] = {0};
        unsigned char first_type = 0;
        if (first != NULL) {
            snprintf(first_name, sizeof(first_name), "%s", first->d_name);
            first_type = first->d_type;
        }
        struct dirent* second = readdir(dir);
        char second_name[8] = {0};
        unsigned char second_type = 0;
        if (second != NULL) {
            snprintf(second_name, sizeof(second_name), "%s", second->d_name);
            second_type = second->d_type;
        }
        check(strcmp(first_name, ".") == 0 && first_type == DT_DIR, "readdir dot");
        check(strcmp(second_name, "..") == 0 && second_type == DT_DIR, "readdir dotdot");
        closedir(dir);
    }

    // posix_spawnp must accept a 255-character candidate when PATH already
    // ends in '/': no separator byte is needed, only the trailing NUL.
    char long_name[250];
    memset(long_name, 'a', 249);
    long_name[249] = 0;
    char long_path[300];
    snprintf(long_path, sizeof(long_path), "/case/%s", long_name);
    const int long_fd = open(long_path, O_CREAT | O_WRONLY, 0644);
    check(long_fd >= 0, "long name create");
    if (long_fd >= 0) { close(long_fd); }
    char* spawnp_argv[] = {(char*)"probe", 0};
    char* spawnp_envp[] = {(char*)"PATH=/case/", 0};
    pid_t spawnp_child = 0;
    errno = 0;
    const int spawnp_error = posix_spawnp(&spawnp_child, long_name, 0, 0,
                                          spawnp_argv, spawnp_envp);
    if (spawnp_error != ENOEXEC) printf("[posix] spawnp_error=%d\n", spawnp_error);
    check(spawnp_error == ENOEXEC, "spawnp trailing-slash PATH boundary");
    if (spawnp_error == 0) { (void)waitpid(spawnp_child, 0, 0); }

    if (failures != 0) { return 1; }
    printf("FILE_POSIX_OK\n");
    fflush(stdout);
    // pipe must take the lowest free descriptors, including closed stdio.
    close(0);
    close(1);
    int pipes[2] = {-1, -1};
    if (pipe(pipes) != 0 || pipes[0] != 0 || pipes[1] != 1) {
        fprintf(stderr, "[posix] FAILED pipe lowest fds errno=%d\n", errno);
        ++failures;
    }
    return failures == 0 ? 0 : 1;
}
