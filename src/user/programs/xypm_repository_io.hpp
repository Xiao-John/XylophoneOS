// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <sys/stat.h>
#include "xypm_repository.hpp"

namespace xypm_repository {
// Explicit ownership permits cleanup after the existing bounded parser's
// longjmp error path; no C++ destructor is crossed by that parser.
inline repository active;
inline FILE* opened_file = nullptr;
inline char* metadata_bytes = nullptr;

inline void cleanup() {
    if (opened_file) { ::fclose(opened_file); opened_file = nullptr; }
    ::free(metadata_bytes);
    metadata_bytes = nullptr;
}

inline bool absolute_path(const char* path, size_t maximum) {
    const size_t length = ::strlen(path);
    if (!length || length > maximum || path[0] != '/') return false;
    if (length == 1) return true;
    if (path[length - 1] == '/') return false;
    const char* component = path + 1;
    for (const char* cursor = component;; ++cursor) {
        const char byte = *cursor;
        if (!byte || byte == '/') {
            const size_t size = size_t(cursor - component);
            if (!size || size > 100 || (size == 1 && component[0] == '.') ||
                (size == 2 && component[0] == '.' && component[1] == '.') || component[size - 1] == '.') return false;
            if (!byte) return true;
            component = cursor + 1;
        } else if (!((byte >= 'a' && byte <= 'z') || (byte >= 'A' && byte <= 'Z') ||
                     (byte >= '0' && byte <= '9') || byte == '_' || byte == '.' || byte == '+' || byte == '-')) return false;
    }
}

inline void package_path(const char* directory, const char* digest, char output[256]) {
    require(absolute_path(directory, 186) && hash_text(digest), "invalid repository path/digest");
    const int length = ::snprintf(output, 256, "%s%s%s.xpk", directory,
                                     directory[1] ? "/" : "", digest);
    require(length > 0 && length < 256, "repository package path too long");
}

inline uint64_t open_regular(const char* path, bool (*path_check)(const char*)) {
    require(!opened_file, "repository file already open");
    require(absolute_path(path, 255) && (!path_check || path_check(path)),
            "repository requires a canonical absolute path");
    opened_file = ::fopen(path, "rb");
    require(opened_file != nullptr, "cannot open repository file");
    struct stat info{};
    require(::fstat(::fileno(opened_file), &info) == 0 && S_ISREG(info.st_mode) && info.st_size >= 0,
            "repository input must be a regular file");
    return uint64_t(info.st_size);
}

inline size_t read_metadata(const char* path, bool (*path_check)(const char*)) {
    const uint64_t size = open_regular(path, path_check);
    require(size <= max_manifest_bytes, "repository metadata exceeds 1 MiB");
    metadata_bytes = static_cast<char*>(::malloc(size ? size_t(size) : 1));
    require(metadata_bytes != nullptr, "cannot allocate repository metadata");
    require(::fread(metadata_bytes, 1, size_t(size), opened_file) == size &&
            ::fgetc(opened_file) == EOF && !::ferror(opened_file),
            "repository metadata changed or could not be read");
    const int closed = ::fclose(opened_file);
    opened_file = nullptr;
    require(closed == 0, "cannot close repository metadata");
    return size_t(size);
}

inline void verify(const char* directory, const char* lock_path, const char* expected_lock_digest,
                   bool (*path_check)(const char*)) {
    cleanup();
    require(absolute_path(directory, 186), "repository directory requires a canonical absolute path");
    struct stat info{};
    require((!path_check || path_check(directory)) && ::stat(directory, &info) == 0 && S_ISDIR(info.st_mode),
            "repository directory is missing or not canonical");
    char index_path[256];
    const int length = ::snprintf(index_path, sizeof(index_path), "%s%sindex.json", directory,
                                     directory[1] ? "/" : "");
    require(length > 0 && size_t(length) < sizeof(index_path), "repository index path too long");
    size_t size = read_metadata(index_path, path_check);
    active.parse_index(metadata_bytes, size);
    ::free(metadata_bytes); metadata_bytes = nullptr;
    size = read_metadata(lock_path, path_check);
    active.parse_lock(metadata_bytes, size, expected_lock_digest);
    ::free(metadata_bytes); metadata_bytes = nullptr;
    for (size_t i = 0; i < active.ordered_count; ++i) {
        char path[256];
        package_path(directory, field(active.ordered[i], "sha256")->text, path);
        const uint64_t package_size = open_regular(path, path_check);
        const auto package = verify_package(opened_file, package_size);
        active.check_package(i, package, package_size);
        const int closed = ::fclose(opened_file);
        opened_file = nullptr;
        require(closed == 0, "cannot close repository package");
    }
}
}
