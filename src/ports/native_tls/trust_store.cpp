// SPDX-License-Identifier: Apache-2.0
#include "trust_store.hpp"

#include <psa/crypto.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace native_tls {
namespace {
constexpr unsigned char magic[8] = {'X', 'O', 'S', 'T', 'R', 'U', 'S', 'T'};
constexpr size_t header_bytes = 32;

uint32_t read_u32(const unsigned char* data) {
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= uint32_t(data[i]) << (8 * i);
    return value;
}

uint64_t read_u64(const unsigned char* data) {
    return uint64_t(read_u32(data)) | (uint64_t(read_u32(data + 4)) << 32);
}

struct certificate_chain {
    mbedtls_x509_crt value{};
    certificate_chain() { mbedtls_x509_crt_init(&value); }
    ~certificate_chain() { mbedtls_x509_crt_free(&value); }
};
}

trust_store::trust_store() { mbedtls_x509_crt_init(&anchors_); }
trust_store::~trust_store() { mbedtls_x509_crt_free(&anchors_); }

trust_store_result trust_store::load_file(const char* path, const trust_store_pin& expected) {
    if (ready()) return trust_store_result::already_loaded;
    if (!path || !*path) return trust_store_result::invalid;
    FILE* file = fopen(path, "rb");
    if (!file) return trust_store_result::unavailable;
    auto* data = static_cast<unsigned char*>(malloc(max_trust_store_bytes + 1));
    if (!data) {
        fclose(file);
        return trust_store_result::unavailable;
    }
    const size_t size = fread(data, 1, max_trust_store_bytes + 1, file);
    const bool failed = ferror(file);
    const int closed = fclose(file);
    const auto result = failed || closed ? trust_store_result::unavailable : load(data, size, expected);
    free(data);
    return result;
}

trust_store_result trust_store::load(const unsigned char* data, size_t size,
                                     const trust_store_pin& expected) {
    if (ready()) return trust_store_result::already_loaded;
    if (!data || size < header_bytes || size > max_trust_store_bytes ||
        !expected.generation || memcmp(data, magic, sizeof magic) ||
        read_u32(data + 8) != 1 || read_u64(data + 24))
        return trust_store_result::invalid;
    const size_t count = read_u32(data + 12);
    if (!count || count > max_trust_anchors) return trust_store_result::invalid;
    if (read_u64(data + 16) != expected.generation) return trust_store_result::pin_mismatch;
    unsigned char digest[32];
    size_t digest_size = 0;
    if (psa_crypto_init() != PSA_SUCCESS ||
        psa_hash_compute(PSA_ALG_SHA_256, data, size, digest, sizeof digest, &digest_size) !=
            PSA_SUCCESS || digest_size != sizeof digest)
        return trust_store_result::unavailable;
    unsigned char difference = 0;
    for (size_t i = 0; i < sizeof digest; ++i) difference |= digest[i] ^ expected.sha256[i];
    if (difference) return trust_store_result::pin_mismatch;

    certificate_chain candidate;
    size_t offset = header_bytes;
    for (size_t index = 0; index < count; ++index) {
        if (size - offset < 4) return trust_store_result::invalid;
        const size_t length = read_u32(data + offset);
        offset += 4;
        if (!length || length > max_trust_anchor_bytes || length > size - offset)
            return trust_store_result::invalid;
        for (const auto* previous = &candidate.value; previous && previous->raw.p;
             previous = previous->next) {
            if (previous->raw.len == length && !memcmp(previous->raw.p, data + offset, length))
                return trust_store_result::duplicate;
        }
        if (mbedtls_x509_crt_parse_der(&candidate.value, data + offset, length))
            return trust_store_result::malformed_certificate;
        const auto* added = &candidate.value;
        while (added->next) added = added->next;
        if (added->raw.len != length) return trust_store_result::malformed_certificate;
        if (!mbedtls_x509_crt_get_ca_istrue(added) ||
            mbedtls_x509_crt_check_key_usage(added, MBEDTLS_X509_KU_KEY_CERT_SIGN))
            return trust_store_result::not_ca;
        offset += length;
    }
    if (offset != size) return trust_store_result::invalid;
    // Transfer the fully parsed chain only after every entry has passed.
    anchors_ = candidate.value;
    mbedtls_x509_crt_init(&candidate.value);
    generation_ = expected.generation;
    count_ = count;
    return trust_store_result::ok;
}

int trust_store::copy_to(mbedtls_x509_crt* destination) const {
    if (!ready() || !destination) return MBEDTLS_ERR_X509_BAD_INPUT_DATA;
    for (const auto* item = &anchors_; item; item = item->next) {
        const int status = mbedtls_x509_crt_parse_der(destination, item->raw.p, item->raw.len);
        if (status) return status;
    }
    return 0;
}
}
