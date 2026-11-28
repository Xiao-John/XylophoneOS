// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "xypm_repository.hpp"

// Content authentication is not an execution or network grant. Only the
// protected provisioning broker can publish the checkpoint/catalog.
namespace xypm_repository_auth {
inline constexpr char signing_domain[] = "XOS-XYPM-RELEASE-V1\0";
inline constexpr size_t release_limit = 4096;
inline constexpr uint64_t integer_limit = 0x7fffffffffffffffULL;

struct bootstrap {
    char repository_id[81]{};
    char target_profile[81]{};
    uint64_t key_epoch = 0;
    uint64_t minimum_sequence = 0;
    uint64_t maximum_validity_seconds = 0;
    uint8_t public_key[32]{};
};
// Read only from the protected broker, never an adjacent writable file.
struct checkpoint {
    uint64_t key_epoch = 0, sequence = 0, last_trusted_unix_seconds = 0;
    char metadata_sha256[65]{};
};
struct release {
    uint64_t key_epoch = 0, sequence = 0, issued_at = 0, expires_at = 0;
    uint64_t generation_id = 0;
    char repository_id[81]{}, target_profile[81]{};
    char index_sha256[65]{}, lock_sha256[65]{}, generation_sha256[65]{};
    char metadata_sha256[65]{};
};

// Upstream OpenSSL EVP. No cryptographic resource survives a longjmp.
bool verify_ed25519(const uint8_t public_key[32], const uint8_t signature[64],
                    const char* bytes, size_t length);

inline bool configured(const bootstrap& trust) {
    unsigned nonzero = 0;
    for (auto byte : trust.public_key) nonzero |= byte;
    return nonzero && xypm_native::identifier(trust.repository_id) &&
           xypm_native::identifier(trust.target_profile) && trust.key_epoch &&
           trust.minimum_sequence && trust.maximum_validity_seconds &&
           trust.maximum_validity_seconds <= 31ULL * 24 * 60 * 60;
}

inline void authenticate(const bootstrap& trust, const char* bytes, size_t length,
                         const uint8_t signature[64], release& result) {
    using namespace xypm_native;
    require(configured(trust), "repository bootstrap trust is not configured");
    require(bytes && length && length <= release_limit, "invalid authenticated metadata size");
    require(verify_ed25519(trust.public_key, signature, bytes, length),
            "repository Ed25519 signature rejected");
    json_parser parser(bytes, length, 0);
    value* object = parser.parse();
    static const char* const fields[] = {"format_version", "repository_id", "target_profile",
        "key_epoch", "sequence", "issued_at", "expires_at", "index_sha256", "lock_sha256",
        "generation_id", "generation_sha256"};
    exact_fields(object, fields, 11);
    require(unsigned_number(field(object, "format_version"), 1, "invalid release format") == 1,
            "invalid release format");
    result = {};
    auto copy = [&](const char* name, char* destination, size_t maximum) {
        const char* source = xypm_repository::string_field(object, name, maximum);
        std::memcpy(destination, source, std::strlen(source) + 1);
    };
    copy("repository_id", result.repository_id, 80);
    copy("target_profile", result.target_profile, 80);
    require(!std::strcmp(result.repository_id, trust.repository_id), "repository identity mismatch");
    require(!std::strcmp(result.target_profile, trust.target_profile), "repository release profile mismatch");
    result.key_epoch = unsigned_number(field(object, "key_epoch"), integer_limit, "invalid release key epoch");
    result.sequence = unsigned_number(field(object, "sequence"), integer_limit, "invalid release sequence");
    result.issued_at = unsigned_number(field(object, "issued_at"), integer_limit, "invalid release issue time");
    result.expires_at = unsigned_number(field(object, "expires_at"), integer_limit, "invalid release expiry");
    result.generation_id = unsigned_number(field(object, "generation_id"), integer_limit, "invalid generation id");
    require(result.key_epoch == trust.key_epoch, "repository key epoch is not bootstrapped");
    require(result.sequence >= trust.minimum_sequence, "repository sequence predates bootstrap floor");
    require(result.generation_id && result.issued_at && result.expires_at > result.issued_at &&
            result.expires_at - result.issued_at <= trust.maximum_validity_seconds,
            "repository validity interval rejected");
    copy("index_sha256", result.index_sha256, 64);
    copy("lock_sha256", result.lock_sha256, 64);
    copy("generation_sha256", result.generation_sha256, 64);
    require(hash_text(result.index_sha256) && hash_text(result.lock_sha256) &&
            hash_text(result.generation_sha256), "invalid authenticated repository digest");
    xypm_repository::digest_bytes(bytes, length, result.metadata_sha256);
}

inline checkpoint accept_freshness(const bootstrap& trust, const release& metadata,
                                  const checkpoint& previous, uint64_t trusted_unix_seconds) {
    using namespace xypm_native;
    require(configured(trust) && trusted_unix_seconds && trusted_unix_seconds <= integer_limit,
            "trusted repository time is unavailable");
    require(trusted_unix_seconds >= previous.last_trusted_unix_seconds,
            "trusted repository clock moved backwards");
    require(metadata.issued_at <= trusted_unix_seconds && trusted_unix_seconds < metadata.expires_at,
            "repository metadata is expired or not yet valid");
    require(previous.key_epoch <= metadata.key_epoch, "repository key epoch rollback rejected");
    if (previous.key_epoch == metadata.key_epoch) {
        require(metadata.sequence >= previous.sequence, "repository metadata rollback rejected");
        if (metadata.sequence == previous.sequence)
            require(hash_text(previous.metadata_sha256) &&
                    !std::strcmp(previous.metadata_sha256, metadata.metadata_sha256),
                    "repository sequence equivocation rejected");
    } else {
        // Rotation requires an independently trusted bootstrap replacement.
        require(metadata.sequence > previous.sequence, "repository epoch rotation reuses sequence");
    }
    checkpoint next{};
    next.key_epoch = metadata.key_epoch;
    next.sequence = metadata.sequence;
    next.last_trusted_unix_seconds = trusted_unix_seconds;
    std::memcpy(next.metadata_sha256, metadata.metadata_sha256, sizeof(next.metadata_sha256));
    return next;
}
}
