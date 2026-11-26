// SPDX-License-Identifier: Apache-2.0
#include "http.hpp"
#include "stream.hpp"
#include "tls_test_root.h"

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

    const char* name = hostname;
    uint32_t expected_flags = 0;
    const bool truncated = !strcmp(scenario, "truncated");
    if (!strcmp(scenario, "wrong-name")) {
        expected_flags = MBEDTLS_X509_BADCERT_CN_MISMATCH;
        name = wrong_name;
    } else if (!strcmp(scenario, "unknown-ca") || !strcmp(scenario, "missing-intermediate")) {
        expected_flags = MBEDTLS_X509_BADCERT_NOT_TRUSTED;
    } else if (!strcmp(scenario, "expired")) {
        expected_flags = MBEDTLS_X509_BADCERT_EXPIRED;
    } else if (!truncated && strcmp(scenario, "valid")) {
        return error("scenario", -1);
    }

    const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
    const auto wall = xos_tls_wall_time(nullptr);
    xos::u32 address = 0;
    if (now < 0 || wall < 0 || !xos::net2::parse_ipv4("10.0.2.2", address))
        return error("platform", -1);
    printf("NATIVE_TLS_CLOCK realtime=%ld\n", static_cast<long>(wall));
    native_tls::stream stream;
    int status = stream.connect(pid, address, static_cast<xos::u16>(port), name,
                                tls_test_root, sizeof(tls_test_root),
                                static_cast<xos::u64>(now) + 20'000'000'000ull);
    const uint32_t verification = stream.verification_flags();
    if (expected_flags) {
        if (status != MBEDTLS_ERR_X509_CERT_VERIFY_FAILED || verification != expected_flags)
            return error("expected-rejection", status, verification);
        printf("NATIVE_TLS_REJECT scenario=%s flags=0x%08x\n", scenario, verification);
        return 0;
    }
    if (status) return error("handshake", status, verification);

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
    printf("NATIVE_TLS_HTTPS status=200 bytes=%zu close_notify=verified\n", parsed.body_length);
    return 0;
}
