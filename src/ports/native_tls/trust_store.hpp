// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <mbedtls/x509_crt.h>
#include <stddef.h>
#include <stdint.h>

namespace native_tls {

inline constexpr size_t max_trust_store_bytes = 1024 * 1024;
inline constexpr size_t max_trust_anchors = 256;
inline constexpr size_t max_trust_anchor_bytes = 16384;

// This pin comes from the trusted application/deployment configuration, never
// from the untrusted bundle beside it. A generation does not authorize itself.
struct trust_store_pin {
    uint64_t generation = 0;
    unsigned char sha256[32]{};
};

enum class trust_store_result {
    ok, invalid, pin_mismatch, malformed_certificate, not_ca, duplicate, unavailable,
    already_loaded,
};

// Immutable after successful load. To update, validate a separate snapshot and
// select its independently authorized pin. Existing streams own their CA copies.
class trust_store {
public:
    trust_store();
    ~trust_store();
    trust_store(const trust_store&) = delete;
    trust_store& operator=(const trust_store&) = delete;

    trust_store_result load(const unsigned char* data, size_t size,
                            const trust_store_pin& expected);
    trust_store_result load_file(const char* path, const trust_store_pin& expected);
    bool ready() const { return count_ != 0; }
    size_t anchor_count() const { return count_; }
    uint64_t generation() const { return generation_; }

private:
    friend class stream;
    int copy_to(mbedtls_x509_crt* destination) const;
    mbedtls_x509_crt anchors_{};
    size_t count_ = 0;
    uint64_t generation_ = 0;
};

}
