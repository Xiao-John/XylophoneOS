// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../browser_http/http.hpp"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Pure navigation policy, shared by the Qt provider and host regression tests.
// Device, connection and address authority remains with the authenticated service.
namespace browser {
inline bool same_origin(const browser_http::url& left, const browser_http::url& right) {
    return left.port == right.port && !strcmp(left.host, right.host);
}

inline bool numeric_host(const char* host) {
    if (!host) return false;
    for (unsigned part = 0; part < 4; ++part) {
        unsigned value = 0, digits = 0;
        const char* start = host;
        while (*host >= '0' && *host <= '9') {
            if (++digits > 3) return false;
            value = value * 10 + static_cast<unsigned>(*host++ - '0');
        }
        if (!digits || value > 255 || (digits > 1 && *start == '0')) return false;
        if (part != 3) { if (*host++ != '.') return false; }
        else if (*host) return false;
    }
    return true;
}

inline browser_http::error remote_location(const char* reference, size_t length,
                                           const browser_http::url* base,
                                           bool resource, browser_http::url& output) {
    browser_http::url candidate{};
    const auto result = base ? browser_http::resolve(*base, reference, length, candidate)
                             : browser_http::parse_url(reference, length, candidate);
    if (result != browser_http::error::ok) return result;
    if (!numeric_host(candidate.host) || (resource && (!base || !same_origin(*base, candidate))))
        return browser_http::error::unsupported;
    output = candidate;
    return browser_http::error::ok;
}

inline browser_http::error remote_resource_location(const char* reference, size_t length,
        const browser_http::url& document, const browser_http::url& base,
        browser_http::url& output) {
    if (!same_origin(document, base)) return browser_http::error::unsupported;
    return remote_location(reference, length, &base, true, output);
}

inline bool format_location(const browser_http::url& input, char* output, size_t capacity) {
    if (!output || !capacity || !memchr(input.host, 0, sizeof(input.host)) ||
        !memchr(input.target, 0, sizeof(input.target)) || !numeric_host(input.host) || !input.port) return false;
    // A valid URL can use fewer bytes than max_url for the target: the authority
    // and optional port count toward the same bound in the existing parser.
    const int size = input.port == 80
        ? snprintf(output, capacity, "http://%s%s", input.host, input.target)
        : snprintf(output, capacity, "http://%s:%u%s", input.host,
                   static_cast<unsigned>(input.port), input.target);
    if (size <= 0 || static_cast<size_t>(size) >= capacity) return false;
    browser_http::url checked{};
    return browser_http::parse_url(output, static_cast<size_t>(size), checked) == browser_http::error::ok;
}

struct navigation_budget {
    static constexpr uint64_t duration_ns = 3000000000ull;
    static constexpr unsigned request_limit = 17; // Document + eight CSS + eight images.
    static constexpr size_t byte_limit = 2u * 1024u * 1024u;
    uint64_t deadline = 0;
    unsigned requests = 0;
    size_t bytes = 0;

    bool begin(int64_t now) {
        *this = {};
        if (now < 0 || static_cast<uint64_t>(now) > uint64_t(INT64_MAX) - duration_ns) return false;
        deadline = static_cast<uint64_t>(now) + duration_ns;
        return true;
    }
    bool request(int64_t now) {
        if (!deadline || now < 0 || static_cast<uint64_t>(now) >= deadline ||
            requests >= request_limit || bytes >= byte_limit) return false;
        ++requests;
        return true;
    }
    bool consume(size_t amount) {
        if (amount > byte_limit - bytes) return false;
        bytes += amount;
        return true;
    }
    size_t remaining_bytes() const { return byte_limit - bytes; }
};
}
