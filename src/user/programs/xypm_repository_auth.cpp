// SPDX-License-Identifier: Apache-2.0
#include "xypm_repository_auth.hpp"
#include <openssl/evp.h>

namespace xypm_repository_auth {
bool verify_ed25519(const uint8_t public_key[32], const uint8_t signature[64],
                    const char* bytes, size_t length) {
    if (!bytes || !length || length > release_limit) return false;
    unsigned char message[sizeof(signing_domain) - 1 + release_limit];
    std::memcpy(message, signing_domain, sizeof(signing_domain) - 1);
    std::memcpy(message + sizeof(signing_domain) - 1, bytes, length);
    EVP_PKEY* key = EVP_PKEY_new_raw_public_key(EVP_PKEY_ED25519, nullptr, public_key, 32);
    EVP_MD_CTX* context = EVP_MD_CTX_new();
    const bool accepted = key && context &&
        EVP_DigestVerifyInit(context, nullptr, nullptr, nullptr, key) == 1 &&
        EVP_DigestVerify(context, signature, 64, message, sizeof(signing_domain) - 1 + length) == 1;
    EVP_MD_CTX_free(context);
    EVP_PKEY_free(key);
    return accepted;
}
}
