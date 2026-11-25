// SPDX-License-Identifier: Apache-2.0
// Execute the actual guest repository verifier on shared fixture bytes.
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
#include "xypm_profile.hpp"
#include "../../../src/user/programs/xypm_repository_io.hpp"

static bool host_path_check(const char* path) {
    // XOS has no symlinks; the host fixture explicitly rejects them to keep
    // package lookup confined when replaying the native code on the host.
    if (!xypm_repository::absolute_path(path, 255)) return false;
    char prefix[256];
    std::strcpy(prefix, path);
    for (char* cursor = prefix + 1;; ++cursor) {
        if (*cursor != '/' && *cursor) continue;
        const char saved = *cursor;
        *cursor = 0;
        struct stat info{};
        const bool valid = ::lstat(prefix, &info) == 0 && !S_ISLNK(info.st_mode);
        *cursor = saved;
        if (!valid) return false;
        if (!saved) break;
    }
    return true;
}

int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) return 2;
    jmp_buf recovery;
    xypm_native::error_target = &recovery;
    if (setjmp(recovery)) {
        xypm_native::error_target = nullptr;
        xypm_repository::cleanup();
        std::fprintf(stderr, "repository rejected: %s\n", xypm_native::last_error);
        return 3;
    }
    if (argc == 4 && !std::strcmp(argv[1], "--size")) {
        xypm_repository::open_regular(argv[2], host_path_check);
        char* end = nullptr;
        const auto size = std::strtoull(argv[3], &end, 10);
        xypm_native::require(end && *end == 0, "invalid fixture size");
        xypm_native::verify_package(xypm_repository::opened_file, size);
        xypm_native::error_target = nullptr;
        xypm_repository::cleanup();
        return 0;
    }
    xypm_repository::verify(argv[1], argv[2], argc == 4 ? argv[3] : nullptr, host_path_check);
    const auto& repository = xypm_repository::active;
    for (size_t i = 0; i < repository.ordered_count; ++i)
        std::printf("%s\n", xypm_native::field(repository.ordered[i], "sha256")->text);
    xypm_native::error_target = nullptr;
    xypm_repository::cleanup();
    return 0;
}
