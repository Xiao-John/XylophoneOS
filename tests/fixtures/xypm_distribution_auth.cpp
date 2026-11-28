// SPDX-License-Identifier: Apache-2.0
#include "xypm_repository_auth.hpp"
#include <cerrno>
#include <openssl/crypto.h>

namespace {
bool digest(const char* text, unsigned char output[32]) {
    if (!xypm_native::hash_text(text)) return false;
    auto nibble = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
    for (unsigned i = 0; i < 32; ++i)
        output[i] = static_cast<unsigned char>((nibble(text[i * 2]) << 4) | nibble(text[i * 2 + 1]));
    return true;
}
bool load(const char* path, void* output, size_t limit, size_t& size) {
    FILE* file = std::fopen(path, "rb");
    if (!file) return false;
    size = std::fread(output, 1, limit, file);
    const bool okay = !std::ferror(file) && std::fgetc(file) == EOF;
    return std::fclose(file) == 0 && okay;
}
}

int main(int argc, char** argv) {
    if (argc == 2 && !std::strcmp(argv[1], "--openssl-version")) {
        std::puts(OpenSSL_version(OPENSSL_VERSION)); return 0;
    }
    if (argc != 12) return 2;
    xypm_repository_auth::bootstrap trust{};
    std::strcpy(trust.repository_id, "xos.test.distribution.only");
    std::strcpy(trust.target_profile, "xos-x86_64-glibc-p1-20261128-v1");
    if (!digest(argv[1], trust.public_key)) return 2;
    trust.key_epoch = std::strtoull(argv[9], nullptr, 10);
    trust.minimum_sequence = std::strtoull(argv[10], nullptr, 10);
    trust.maximum_validity_seconds = std::strtoull(argv[11], nullptr, 10);
    char body[8192];
    unsigned char signature[64];
    size_t length = 0, signature_length = 0;
    if (!load(argv[2], body, sizeof(body), length) ||
        !load(argv[3], signature, sizeof(signature), signature_length) || signature_length != sizeof(signature))
        return 2;
    xypm_repository_auth::checkpoint previous{};
    previous.key_epoch = std::strtoull(argv[5], nullptr, 10);
    previous.sequence = std::strtoull(argv[6], nullptr, 10);
    previous.last_trusted_unix_seconds = std::strtoull(argv[7], nullptr, 10);
    if (std::strlen(argv[8]) >= sizeof(previous.metadata_sha256)) return 2;
    std::strcpy(previous.metadata_sha256, argv[8]);
    jmp_buf rejected;
    xypm_native::error_target = &rejected;
    if (setjmp(rejected)) {
        xypm_native::error_target = nullptr;
        std::fprintf(stderr, "rejected: %s\n", xypm_native::last_error);
        return 3;
    }
    xypm_repository_auth::release accepted{};
    xypm_repository_auth::authenticate(trust, body, length, signature, accepted);
    const auto next = xypm_repository_auth::accept_freshness(
        trust, accepted, previous, std::strtoull(argv[4], nullptr, 10));
    xypm_native::error_target = nullptr;
    std::printf("accepted sequence=%llu time=%llu metadata=%s\n",
        static_cast<unsigned long long>(next.sequence),
        static_cast<unsigned long long>(next.last_trusted_unix_seconds), next.metadata_sha256);
    return 0;
}
