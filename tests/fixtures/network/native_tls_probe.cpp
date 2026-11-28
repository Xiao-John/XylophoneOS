// SPDX-License-Identifier: Apache-2.0
#include "https_transport.hpp"
#include "stream.hpp"
#include "tls_test_root.h"
#ifdef XOS_TLS_TRUST_STORE_PROBE
#include "tls_trust_fixtures.hpp"
#endif

#include <psa/crypto.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

namespace {
constexpr char hostname[] = "tls.xos.test";
constexpr char wrong_name[] = "other.xos.test";

int error(const char* stage, int status, uint32_t flags = 0) {
    printf("NATIVE_TLS_ERROR stage=%s status=%d flags=0x%08x\n", stage, status, flags);
    return 1;
}

unsigned long number(const char* text, unsigned long maximum) {
    char* end = nullptr;
    const auto value = strtoul(text, &end, 10);
    return *text && *text >= '0' && *text <= '9' && !*end && value <= maximum ? value : 0;
}

bool has_no_verified_peer(const native_tls::stream& stream) {
    const auto peer = stream.verified_peer_leaf_der();
    return !peer.data && !peer.size;
}

int record_verified_peer(const native_tls::stream& stream) {
    const auto peer = stream.verified_peer_leaf_der();
    if (!peer.data || !peer.size)
        return error("peer-leaf-unavailable", -1);

    unsigned char digest[PSA_HASH_LENGTH(PSA_ALG_SHA_256)];
    size_t size = 0;
    const auto status = psa_hash_compute(PSA_ALG_SHA_256, peer.data, peer.size,
                                         digest, sizeof(digest), &size);
    if (status != PSA_SUCCESS || size != sizeof(digest))
        return error("peer-leaf-hash", status);
    printf("NATIVE_TLS_PEER_LEAF_SHA256 ");
    for (unsigned char byte : digest)
        printf("%02x", static_cast<unsigned>(byte));
    putchar('\n');
    return 0;
}
constexpr size_t large_body_size = 2 * 1024 * 1024 + 7;
unsigned char header_workspace[browser_http::max_headers];

int streamed_https(unsigned long pid, unsigned long port, const char* nonce, bool truncated) {
    const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
    const auto wall = xos_tls_wall_time(nullptr);
    xos::u32 address = 0;
    if (now < 0 || wall < 0 || !xos::net2::parse_ipv4("10.0.2.2", address))
        return error("platform", -1);
    printf("NATIVE_TLS_CLOCK realtime=%ld\n", static_cast<long>(wall));
    browser_http::url target{};
    target.protocol = browser_http::scheme::https;
    target.port = static_cast<xos::u16>(port);
    memcpy(target.host, hostname, sizeof hostname);
    snprintf(target.target, sizeof target.target, "/%s", nonce);
    struct body_state { const char* nonce; size_t received; } body{nonce, 0};
    browser_http::response response{};
    const auto status = browser_http::fetch_https_stream(
        {pid, address, tls_test_root, sizeof tls_test_root, native_tls::route_source::pinned},
        target, [](void* context, const unsigned char* bytes, xos::u32 size) -> xos::i64 {
            auto& state = *static_cast<body_state*>(context);
            for (xos::u32 i = 0; i < size; ++i)
                if (bytes[i] != static_cast<unsigned char>(state.nonce[state.received++ % 32]))
                    return xos::net2::invalid;
            return size;
        }, &body, header_workspace, sizeof header_workspace, large_body_size,
        static_cast<xos::u64>(now) + 180'000'000'000ull, response);
    if (truncated) {
        if (status != xos::net2::io || body.received != large_body_size - 1 || response.status)
            return error("stream-truncated", static_cast<int>(status));
        puts("NATIVE_TLS_REJECT scenario=stream-truncated");
    } else {
        if (status || response.status != 200 || response.body_length != large_body_size ||
            body.received != large_body_size)
        {
            printf("NATIVE_TLS_STREAM_PROGRESS bytes=%zu\n", body.received);
            return error("stream-body", static_cast<int>(status));
        }
        printf("NATIVE_TLS_HTTPS status=200 bytes=%zu close_notify=verified\n", body.received);
    }
    return 0;
}

#ifdef XOS_TLS_TRUST_STORE_PROBE
int trust_store_selftest() {
    using native_tls::trust_store_result;
    if (psa_crypto_init() != PSA_SUCCESS) return error("trust-selftest-crypto", -1);
    unsigned checks = 0;
    const auto check = [&](const unsigned char* data, size_t length, trust_store_result expected) {
        native_tls::trust_store_pin pin{};
        pin.generation = 1;
        size_t digest_size = 0;
        if (psa_hash_compute(PSA_ALG_SHA_256, data, length, pin.sha256, sizeof pin.sha256,
                             &digest_size) != PSA_SUCCESS || digest_size != sizeof pin.sha256)
            return false;
        native_tls::trust_store candidate;
        const auto result = candidate.load(data, length, pin);
        if (result != expected || candidate.ready() != (expected == trust_store_result::ok)) return false;
        ++checks;
        return true;
    };
    unsigned char changed[sizeof tls_store_fixture * 2]{};
    const size_t length = sizeof tls_store_fixture;
    if (!check(tls_store_fixture, length, trust_store_result::ok) ||
        !check(tls_store_fixture, 0, trust_store_result::invalid) ||
        !check(tls_store_fixture, 31, trust_store_result::invalid) ||
        !check(tls_store_fixture, 32, trust_store_result::invalid) ||
        !check(tls_store_fixture, length - 1, trust_store_result::invalid))
        return error("trust-selftest-length", -1);
    const unsigned offsets[]{0u, 8u, 12u, 24u};
    for (unsigned offset : offsets) {
        memcpy(changed, tls_store_fixture, length);
        changed[offset] = offset == 12 ? 0 : 255;
        if (!check(changed, length, trust_store_result::invalid))
            return error("trust-selftest-header", offset);
    }
    memcpy(changed, tls_store_fixture, length);
    changed[16] = 2;
    if (!check(changed, length, trust_store_result::pin_mismatch)) return error("trust-selftest-generation", -1);
    memcpy(changed, tls_store_fixture, length);
    memset(changed + 32, 255, 4);
    if (!check(changed, length, trust_store_result::invalid)) return error("trust-selftest-entry-length", -1);
    memcpy(changed, tls_store_fixture, length);
    changed[36] = 0;
    if (!check(changed, length, trust_store_result::malformed_certificate)) return error("trust-selftest-der", -1);
    memcpy(changed, tls_store_fixture, length);
    changed[length] = 0;
    if (!check(changed, length + 1, trust_store_result::invalid)) return error("trust-selftest-trailing", -1);
    const size_t first_length = size_t(tls_store_fixture[32]) | (size_t(tls_store_fixture[33]) << 8) |
        (size_t(tls_store_fixture[34]) << 16) | (size_t(tls_store_fixture[35]) << 24);
    if (first_length + 36 > length) return error("trust-selftest-fixture", -1);
    memcpy(changed, tls_store_fixture, first_length + 36);
    memcpy(changed + first_length + 36, tls_store_fixture + 32, first_length + 4);
    if (!check(changed, 32 + (first_length + 4) * 2, trust_store_result::duplicate))
        return error("trust-selftest-duplicate", -1);
    memcpy(changed, tls_store_fixture, 32);
    changed[12] = 1;
    for (unsigned i = 0; i < 4; ++i) changed[32 + i] = (sizeof tls_leaf_fixture >> (8 * i)) & 255;
    memcpy(changed + 36, tls_leaf_fixture, sizeof tls_leaf_fixture);
    if (!check(changed, 36 + sizeof tls_leaf_fixture, trust_store_result::not_ca))
        return error("trust-selftest-leaf-is-not-anchor", -1);
    printf("TRUST_STORE_SELFTEST_PASS checks=%u\n", checks);
    return 0;
}
#endif
}

int main(int argc, char** argv) {
    if (argc != 5) return error("arguments", argc);
    const auto pid = number(argv[1], ~0ul);
    const auto port = number(argv[2], 65535);
    const char* scenario = argv[3];
    const char* nonce = argv[4];
    if (!pid || !port || strlen(nonce) != 32 ||
        strspn(nonce, "0123456789abcdef") != 32)
        return error("arguments", -1);

    if (!strcmp(scenario, "stream") || !strcmp(scenario, "stream-truncated"))
        return streamed_https(pid, port, nonce, !strcmp(scenario, "stream-truncated"));

    const char* name = hostname;
    const char* verification_case = scenario;
#ifdef XOS_TLS_TRUST_STORE_PROBE
    if (!strcmp(scenario, "store-selftest")) return trust_store_selftest();
#ifdef XOS_TLS_PUBLIC_STORE_FIXTURE
    if (!strcmp(scenario, "store-public")) {
        native_tls::trust_store public_store;
        const auto result = public_store.load_file("/tls-public-roots.bin", tls_public_store_pin);
        if (result != native_tls::trust_store_result::ok || public_store.anchor_count() != tls_public_store_count)
            return error("public-trust-store", static_cast<int>(result));
        printf("TRUST_PUBLIC_STORE_PASS generation=%lu count=%zu\n", public_store.generation(), public_store.anchor_count());
        return 0;
    }
#endif
    native_tls::trust_store store;
    const bool from_store = !strncmp(scenario, "store-", 6);
    if (from_store) {
        verification_case = scenario + 6;
        const bool updated = !strcmp(verification_case, "removed") || !strcmp(verification_case, "updated");
        const bool tampered = !strcmp(verification_case, "tampered");
        const bool stale = !strcmp(verification_case, "stale");
        const char* path = tampered ? "/tls-roots-bad.bin" : updated ? "/tls-roots-2.bin" : "/tls-roots-1.bin";
        const auto& pin = updated || stale ? tls_store_pin_2 : tls_store_pin_1;
        const auto loaded = store.load_file(path, pin);
        if (tampered || stale) {
            if (loaded != native_tls::trust_store_result::pin_mismatch || store.ready())
                return error("trust-rejection", static_cast<int>(loaded));
            printf("TRUST_STORE_REJECT scenario=%s\n", scenario);
            return 0;
        }
        if (loaded != native_tls::trust_store_result::ok || store.generation() != pin.generation ||
            store.anchor_count() != (updated ? 1u : 2u))
            return error("trust-load", static_cast<int>(loaded));
        if (store.load_file("/tls-roots-bad.bin", pin) != native_tls::trust_store_result::already_loaded ||
            !store.ready() || store.generation() != pin.generation)
            return error("trust-immutable", -1);
        printf("TRUST_STORE_READY generation=%lu count=%zu\n", store.generation(), store.anchor_count());
        if (!strcmp(verification_case, "removed")) verification_case = "unknown-ca";
        if (!strcmp(verification_case, "second") || !strcmp(verification_case, "updated") ||
            !strcmp(verification_case, "rollback")) verification_case = "valid";
    }
#endif
    uint32_t expected_flags = 0;
    const bool truncated = !strcmp(verification_case, "truncated");
    if (!strcmp(verification_case, "wrong-name")) {
        expected_flags = MBEDTLS_X509_BADCERT_CN_MISMATCH;
        name = wrong_name;
    } else if (!strcmp(verification_case, "unknown-ca") || !strcmp(verification_case, "missing-intermediate")) {
        expected_flags = MBEDTLS_X509_BADCERT_NOT_TRUSTED;
    } else if (!strcmp(verification_case, "expired")) {
        expected_flags = MBEDTLS_X509_BADCERT_EXPIRED;
    } else if (!truncated && strcmp(verification_case, "valid")) {
        return error("scenario", -1);
    }

    const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
    const auto wall = xos_tls_wall_time(nullptr);
    xos::u32 address = 0;
    if (now < 0 || wall < 0 || !xos::net2::parse_ipv4("10.0.2.2", address))
        return error("platform", -1);
    printf("NATIVE_TLS_CLOCK realtime=%ld\n", static_cast<long>(wall));
    native_tls::stream stream;
    if (!has_no_verified_peer(stream))
        return error("peer-before-handshake", -1);
    int status =
#ifdef XOS_TLS_TRUST_STORE_PROBE
        from_store ? stream.connect(pid, address, static_cast<xos::u16>(port), name, store,
                                     static_cast<xos::u64>(now) + 20'000'000'000ull) :
#endif
        stream.connect(pid, address, static_cast<xos::u16>(port), name,
                                tls_test_root, sizeof(tls_test_root),
                                static_cast<xos::u64>(now) + 20'000'000'000ull);
    const uint32_t verification = stream.verification_flags();
    if (expected_flags) {
        if (status != MBEDTLS_ERR_X509_CERT_VERIFY_FAILED || verification != expected_flags)
            return error("expected-rejection", status, verification);
        if (!has_no_verified_peer(stream))
            return error("peer-after-rejection", -1);
        printf("NATIVE_TLS_REJECT scenario=%s flags=0x%08x\n", scenario, verification);
        return 0;
    }
    if (status) return error("handshake", status, verification);
    if (record_verified_peer(stream))
        return 1;

    char request[192];
    status = snprintf(request, sizeof(request),
                      "GET /%s HTTP/1.1\r\nHost: %s:%lu\r\nConnection: close\r\n\r\n",
                      nonce, name, port);
    if (status <= 0 || static_cast<size_t>(status) >= sizeof(request))
        return error("request", status);
    const size_t length = static_cast<size_t>(status);
    const auto* bytes = reinterpret_cast<const unsigned char*>(request);
    for (size_t sent = 0; sent < length;) {
        status = stream.write(bytes + sent, length - sent);
        if (status <= 0) return error("write", status);
        sent += static_cast<size_t>(status);
    }

    unsigned char response[2048];
    size_t received = 0;
    do {
        status = stream.read(response + received, sizeof(response) - received);
        if (truncated && status == MBEDTLS_ERR_SSL_CONN_EOF) {
            if (!has_no_verified_peer(stream))
                return error("peer-after-truncation", -1);
            printf("NATIVE_TLS_REJECT scenario=truncated status=%d\n", status);
            return 0;
        }
        if (status < 0) return error("read", status);
        received += static_cast<size_t>(status);
        if (received == sizeof(response)) return error("response-budget", -1);
    } while (status);
    browser_http::response parsed;
    if (truncated || browser_http::parse_response(response, received, true, parsed) !=
            browser_http::error::ok || parsed.status != 200 || parsed.body_length != 32 ||
        memcmp(response + parsed.body_offset, nonce, 32))
        return error("http", static_cast<int>(parsed.status));
    status = stream.finish();
    if (status) return error("finish", status);
    if (!has_no_verified_peer(stream))
        return error("peer-after-finish", -1);
    printf("NATIVE_TLS_HTTPS status=200 bytes=%zu close_notify=verified\n", parsed.body_length);
    return 0;
}
