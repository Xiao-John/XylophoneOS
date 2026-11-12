// SPDX-License-Identifier: Apache-2.0
#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

namespace {
constexpr unsigned paged_file_count = 20;
constexpr unsigned long_name_chars = 76;
constexpr unsigned long_name_bytes = 1 + long_name_chars * 3 + 2;

int write_byte_file(const char* path, char value) {
    const int fd = open(path, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0) return -1;
    const int result = write(fd, &value, 1) == 1 && close(fd) == 0 ? 0 : -1;
    return result;
}

void make_paged_name(char* output, unsigned index) {
    output[0] = 'p';
    unsigned at = 1;
    for (unsigned i = 0; i < long_name_chars; ++i) {
        output[at++] = static_cast<char>(0xe5);
        output[at++] = static_cast<char>(0x90);
        output[at++] = static_cast<char>(0x8d);
    }
    output[at++] = static_cast<char>('0' + index / 10);
    output[at++] = static_cast<char>('0' + index % 10);
    output[at] = '\0';
}

bool test_non_bmp_name() {
    const char* original = "/中文/🧪-𠮷.txt";
    const char* renamed = "/中文/🧪-𠮷-renamed.txt";
    if (write_byte_file(original, 'N') != 0 || rename(original, renamed) != 0) return false;
    const int fd = open(renamed, O_RDONLY);
    char value = 0;
    if (fd < 0 || read(fd, &value, 1) != 1 || value != 'N' || close(fd) != 0) return false;
    DIR* dir = opendir("/中文");
    if (!dir) return false;
    bool found = false;
    while (struct dirent* entry = readdir(dir)) {
        if (!strcmp(entry->d_name, "🧪-𠮷-renamed.txt")) found = true;
    }
    if (closedir(dir) != 0 || !found || unlink(renamed) != 0) return false;
    return true;
}

bool test_path_byte_boundary() {
    char path[257] = "/中文/";
    unsigned at = 8; // slash + two CJK code points + slash
    for (unsigned i = 0; i < 80; ++i) {
        path[at++] = static_cast<char>(0xe5);
        path[at++] = static_cast<char>(0x90);
        path[at++] = static_cast<char>(0x8d);
    }
    const char suffix[] = "abcdefg";
    for (unsigned i = 0; i < sizeof(suffix) - 1; ++i) path[at++] = suffix[i];
    path[at] = '\0';
    if (at != 255 || write_byte_file(path, 'B') != 0) return false;
    char valid_path[257]{};
    memcpy(valid_path, path, at + 1);
    const int fd = open(path, O_RDONLY);
    char value = 0;
    if (fd < 0 || read(fd, &value, 1) != 1 || value != 'B' || close(fd) != 0) return false;

    path[at++] = 'h';
    path[at] = '\0';
    const int too_long = open(path, O_CREAT | O_WRONLY, 0644);
    if (too_long >= 0) { (void)close(too_long); return false; }

    DIR* dir = opendir("/中文");
    if (!dir) return false;
    bool found = false;
    while (struct dirent* entry = readdir(dir)) {
        if (strlen(entry->d_name) == 247 &&
            !memcmp(entry->d_name, path + 8, 240) &&
            !memcmp(entry->d_name + 240, suffix, 7)) { found = true; }
    }
    return closedir(dir) == 0 && found && unlink(valid_path) == 0;
}

bool test_long_directory_pages() {
    char path[256] = "/中文/";
    unsigned at = 8;
    for (unsigned index = 0; index < paged_file_count; ++index) {
        char name[long_name_bytes + 1]{};
        make_paged_name(name, index);
        memcpy(path + at, name, sizeof(name));
        if (write_byte_file(path, static_cast<char>('A' + index)) != 0) return false;
    }

    DIR* dir = opendir("/中文");
    if (!dir) return false;
    bool seen[paged_file_count]{};
    unsigned found = 0;
    while (struct dirent* entry = readdir(dir)) {
        for (unsigned index = 0; index < paged_file_count; ++index) {
            char expected[long_name_bytes + 1]{};
            make_paged_name(expected, index);
            if (!strcmp(entry->d_name, expected)) {
                if (seen[index]) { (void)closedir(dir); return false; }
                seen[index] = true;
                ++found;
            }
        }
    }
    if (closedir(dir) != 0 || found != paged_file_count) return false;
    for (bool item : seen) if (!item) return false;

    for (unsigned index = 0; index < paged_file_count; ++index) {
        char name[long_name_bytes + 1]{};
        make_paged_name(name, index);
        memcpy(path + at, name, sizeof(name));
        const int fd = open(path, O_RDONLY);
        char value = 0;
        if (fd < 0 || read(fd, &value, 1) != 1 || value != static_cast<char>('A' + index) ||
            close(fd) != 0 || unlink(path) != 0) return false;
    }
    return true;
}
}

int main() {
    const char* name = "/中文/程序.txt";
    int fd = open(name, O_CREAT | O_WRONLY | O_TRUNC, 0644);
    if (fd < 0 || write(fd, "runtime", 7) != 7 || close(fd) != 0) return 1;
    DIR* dir = opendir("/中文");
    if (!dir) return 2;
    bool seen = false;
    while (struct dirent* entry = readdir(dir)) {
        if (!strcmp(entry->d_name, "程序.txt")) seen = true;
    }
    if (closedir(dir) != 0 || !seen) return 3;
    if (rename(name, "/中文/更名.txt") != 0) return 4;
    fd = open("/中文/更名.txt", O_RDONLY);
    char value[8]{};
    if (fd < 0 || read(fd, value, 7) != 7 || memcmp(value, "runtime", 7) || close(fd)) return 5;
    if (open("/中文/\xff.txt", O_CREAT | O_WRONLY, 0644) >= 0) return 6;
    if (!test_non_bmp_name()) return 7;
    puts("UTF8_M2_NONBMP_OK");
    if (!test_path_byte_boundary()) return 8;
    puts("UTF8_M2_PATH_BOUNDARY_OK");
    if (!test_long_directory_pages()) return 9;
    puts("UTF8_M2_DIRECTORY_PAGING_OK");
    if (unlink("/中文/更名.txt") != 0) return 10;
    puts("UTF8_LIBC_OK");
    return 0;
}
