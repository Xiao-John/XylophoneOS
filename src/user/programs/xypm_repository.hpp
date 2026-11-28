// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "xypm_native.hpp"

// Metadata-only repository policy. The index lives in JSON arena 1; the lock
// and each verified package reuse arena 0. Copy the selected digest before a
// P2 transaction reuses arena 1 for the installed database.
namespace xypm_repository {
using namespace xypm_native;
constexpr size_t max_entries = 256;
constexpr size_t max_selected = 64;

inline void digest_bytes(const void* bytes, size_t length, char output[65]) {
    sha256 hash;
    uint8_t digest[32];
    hash.update(bytes, length);
    hash.finish(digest);
    hex_digest(digest, output);
}

inline const char* string_field(value* object, const char* name, size_t limit = 1024) {
    return text(need(object, name, kind::string), name, limit);
}

inline void validate_identity(value* item) {
    require(identifier(string_field(item, "id", 80)), "invalid repository package id");
    string_field(item, "upstream_version");
    unsigned_number(field(item, "revision"), 0x7fffffff, "invalid repository revision");
    require(hash_text(string_field(item, "sha256", 64)), "invalid repository package hash");
}

inline bool same_identity(value* left, value* right) {
    return !::strcmp(field(left, "id")->text, field(right, "id")->text) &&
           !::strcmp(field(left, "upstream_version")->text, field(right, "upstream_version")->text) &&
           field(left, "revision")->number == field(right, "revision")->number &&
           !::strcmp(field(left, "sha256")->text, field(right, "sha256")->text);
}

struct repository {
    value* entries[max_entries]{};
    value* ordered[max_selected]{};
    uint8_t states[max_entries]{};
    size_t entry_count = 0, selected_count = 0, ordered_count = 0;
    const char* profile = nullptr;
    char index_digest[65]{};
    char lock_digest[65]{};

    size_t find_digest(const char* digest) const {
        size_t low = 0, high = entry_count;
        while (low < high) {
            const size_t middle = low + (high - low) / 2;
            if (::strcmp(field(entries[middle], "sha256")->text, digest) < 0) low = middle + 1;
            else high = middle;
        }
        return low < entry_count && !::strcmp(field(entries[low], "sha256")->text, digest)
                   ? low : SIZE_MAX;
    }

    void parse_index(const char* bytes, size_t length) {
        *this = {};
        digest_bytes(bytes, length, index_digest);
        json_parser parser(bytes, length, 1);
        value* index = parser.parse();
        static const char* const top[] = {"format_version", "target_profile", "packages"};
        exact_fields(index, top, 3);
        require(unsigned_number(field(index, "format_version"), 1, "invalid repository version") == 1,
                "invalid repository version");
        profile = string_field(index, "target_profile", 80);
        require(identifier(profile), "invalid repository profile");
#ifdef XYP_PACKAGE_PROFILE_ID
        require(!::strcmp(profile, XYP_PACKAGE_PROFILE_ID), "repository target profile mismatch");
#endif
        const char* previous = "";
        for (value* item = need(index, "packages", kind::array)->child; item; item = item->next) {
            require(entry_count < max_entries, "repository exceeds 256 packages");
            static const char* const keys[] = {"id", "upstream_version", "revision", "sha256",
                                               "size", "required_features", "runtime_dependencies"};
            exact_fields(item, keys, 7);
            validate_identity(item);
            const char* digest = field(item, "sha256")->text;
            require(::strcmp(previous, digest) < 0, "repository hashes must be unique and sorted");
            previous = digest;
            const uint64_t size = unsigned_number(field(item, "size"), max_archive_bytes,
                                                  "invalid repository package size");
            require(size && size % 512 == 0, "invalid repository package alignment");
            for (size_t i = 0; i < entry_count; ++i) {
                value* earlier = entries[i];
                require(::strcmp(field(earlier, "id")->text, field(item, "id")->text) ||
                        ::strcmp(field(earlier, "upstream_version")->text, field(item, "upstream_version")->text) ||
                        field(earlier, "revision")->number != field(item, "revision")->number,
                        "ambiguous package version/revision");
            }
            entries[entry_count++] = item;
            size_t count = 0;
            previous = "";
            for (value* feature = need(item, "required_features", kind::array)->child; feature; feature = feature->next) {
                require(++count <= 64, "too many repository features");
                const char* name = text(feature, "feature", 80);
                require(identifier(name) && ::strcmp(previous, name) < 0,
                        "invalid/duplicate/unsorted repository feature");
#ifdef XYP_PACKAGE_FEATURES
                require(XYP_PACKAGE_FEATURES(name), "required repository feature unavailable");
#endif
                previous = name;
            }
            count = 0;
            previous = "";
            for (value* dependency = need(item, "runtime_dependencies", kind::array)->child;
                 dependency; dependency = dependency->next) {
                require(++count <= 128, "too many repository dependencies");
                static const char* const keys[] = {"id", "upstream_version", "revision", "sha256"};
                exact_fields(dependency, keys, 4);
                validate_identity(dependency);
                const char* name = field(dependency, "id")->text;
                require(::strcmp(previous, name) < 0 && ::strcmp(name, field(item, "id")->text),
                        "duplicate/unsorted/self repository dependency");
                previous = name;
            }
            previous = digest;
        }
        require(entry_count > 0, "empty repository");
    }

    void visit(size_t position) {
        require(position < entry_count, "missing repository root or dependency");
        require(states[position] != 1, "repository dependency cycle");
        if (states[position] == 2) return;
        require(++selected_count <= max_selected, "lock dependency closure exceeds 64 packages");
        value* item = entries[position];
        for (size_t i = 0; i < entry_count; ++i) {
            if (i != position && states[i])
                require(::strcmp(field(entries[i], "id")->text, field(item, "id")->text),
                        "dependency closure selects conflicting package versions");
        }
        states[position] = 1;
        for (value* dependency = field(item, "runtime_dependencies")->child; dependency; dependency = dependency->next) {
            const size_t next = find_digest(field(dependency, "sha256")->text);
            require(next < entry_count && same_identity(entries[next], dependency),
                    "repository dependency identity mismatch or missing package");
            visit(next);
        }
        states[position] = 2;
        ordered[ordered_count++] = item;
    }

    void parse_lock(const char* bytes, size_t length, const char* expected_digest = nullptr) {
        digest_bytes(bytes, length, lock_digest);
        if (expected_digest)
            require(hash_text(expected_digest) && !::strcmp(expected_digest, lock_digest),
                    "lock SHA-256 mismatch");
        json_parser parser(bytes, length, 0);
        value* lock = parser.parse();
        static const char* const keys[] = {"format_version", "target_profile", "index_sha256", "roots", "packages"};
        exact_fields(lock, keys, 5);
        require(unsigned_number(field(lock, "format_version"), 1, "invalid lock version") == 1,
                "invalid lock version");
        require(!::strcmp(string_field(lock, "target_profile", 80), profile), "lock target profile mismatch");
        require(!::strcmp(string_field(lock, "index_sha256", 64), index_digest), "lock/index SHA-256 mismatch");
        ::memset(states, 0, sizeof(states));
        selected_count = ordered_count = 0;
        size_t roots = 0;
        const char* previous = "";
        for (value* root = need(lock, "roots", kind::array)->child; root; root = root->next) {
            const char* digest = text(root, "root", 64);
            require(++roots <= max_selected && hash_text(digest) && ::strcmp(previous, digest) < 0,
                    "invalid/duplicate/unsorted lock root");
            previous = digest;
            visit(find_digest(digest));
        }
        require(roots > 0, "empty lock roots");
        size_t count = 0;
        for (value* chosen = need(lock, "packages", kind::array)->child; chosen; chosen = chosen->next) {
            require(count < ordered_count &&
                    !::strcmp(text(chosen, "selected hash", 64), field(ordered[count], "sha256")->text),
                    "lock is not the exact deterministic dependency closure");
            ++count;
        }
        require(count == ordered_count, "lock omits selected package");
    }

    void check_package(size_t ordinal, const verified_package& package, uint64_t size) const {
        require(ordinal < ordered_count, "invalid selected package ordinal");
        value* entry = ordered[ordinal];
        value* manifest = package.manifest;
        require(size == uint64_t(field(entry, "size")->number) &&
                !::strcmp(package.digest, field(entry, "sha256")->text), "repository package size/hash mismatch");
        require(!::strcmp(field(manifest, "target_profile")->text, profile) &&
                !::strcmp(field(manifest, "id")->text, field(entry, "id")->text) &&
                !::strcmp(field(manifest, "upstream_version")->text, field(entry, "upstream_version")->text) &&
                field(manifest, "revision")->number == field(entry, "revision")->number,
                "repository entry differs from package identity/profile");
        size_t expected = 0, actual = 0;
        for (value* feature = field(entry, "required_features")->child; feature; feature = feature->next) ++expected;
        for (value* feature = field(manifest, "required_features")->child; feature; feature = feature->next) {
            ++actual;
            bool found = false;
            for (value* item = field(entry, "required_features")->child; item; item = item->next)
                if (!::strcmp(feature->text, item->text)) found = true;
            require(found, "repository feature differs from package");
        }
        require(expected == actual, "repository feature count differs from package");
        expected = actual = 0;
        for (value* dependency = field(entry, "runtime_dependencies")->child; dependency; dependency = dependency->next) ++expected;
        for (value* dependency = field(manifest, "runtime_dependencies")->child; dependency; dependency = dependency->next) {
            ++actual;
            bool found = false;
            for (value* item = field(entry, "runtime_dependencies")->child; item; item = item->next)
                if (same_identity(dependency, item)) found = true;
            require(found, "repository dependency differs from package");
        }
        require(expected == actual, "repository dependency count differs from package");
    }
};
}
