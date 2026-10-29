// SPDX-License-Identifier: Apache-2.0
#include "http.hpp"

namespace browser_http {
namespace {
char lower(char c) { return c >= 'A' && c <= 'Z' ? char(c + ('a' - 'A')) : c; }
bool equal(const char* a, size_t n, const char* b) {
    size_t i = 0;
    for (; i < n && b[i]; ++i) if (lower(a[i]) != b[i]) return false;
    return i == n && b[i] == 0;
}
bool starts(const char* a, size_t n, const char* b) {
    size_t i = 0;
    for (; b[i]; ++i) if (i >= n || lower(a[i]) != b[i]) return false;
    return true;
}
size_t length(const char* s, size_t cap) { size_t n = 0; while (n < cap && s[n]) ++n; return n; }
bool copy(char* out, size_t cap, const char* in, size_t n) {
    if (n >= cap) return false;
    for (size_t i = 0; i < n; ++i) out[i] = in[i];
    out[n] = 0; return true;
}
int hex(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    c = lower(c); return c >= 'a' && c <= 'f' ? c - 'a' + 10 : -1;
}
bool safe_reference(const char* s, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        const unsigned c = static_cast<unsigned char>(s[i]);
        if (c <= 32 || c >= 127 || c == '\\') return false;
        if (c == '%') {
            if (i + 2 >= n || hex(s[i + 1]) < 0 || hex(s[i + 2]) < 0) return false;
            const int decoded = hex(s[i + 1]) * 16 + hex(s[i + 2]);
            if (decoded < 32 || decoded == 127) return false;
            i += 2;
        }
    }
    return true;
}
// RFC 3986 dot-segment removal for absolute paths; queries remain byte exact.
error target(const char* s, size_t n, char* out) {
    size_t fragment = 0;
    while (fragment < n && s[fragment] != '#') ++fragment;
    n = fragment;
    size_t query = 0;
    while (query < n && s[query] != '?') ++query;
    if (!n || s[0] == '?') {
        out[0] = '/';
        return copy(out + 1, max_url, s, n) ? error::ok : error::too_large;
    }
    if (s[0] != '/') return error::invalid;
    // Preserve repeated slashes (server semantics), removing only literal . / .. .
    size_t used = 1, pos = 1;
    out[0] = '/';
    while (pos < query) {
        size_t end = pos;
        while (end < query && s[end] != '/') ++end;
        const size_t bytes = end - pos;
        const bool dot = bytes == 1 && s[pos] == '.';
        const bool parent = bytes == 2 && s[pos] == '.' && s[pos + 1] == '.';
        if (parent) {
            if (used > 1 && out[used - 1] == '/') --used;
            while (used > 1 && out[used - 1] != '/') --used;
        } else if (!dot) {
            if (used + bytes + (end < query ? 1u : 0u) > max_url) return error::too_large;
            for (size_t i = pos; i < end; ++i) out[used++] = s[i];
            if (end < query) out[used++] = '/';
        }
        pos = end + 1;
    }
    if (used + n - query > max_url) return error::too_large;
    for (size_t i = query; i < n; ++i) out[used++] = s[i];
    out[used] = 0; return error::ok;
}
bool token(unsigned char c) {
    if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')) return true;
    const char* punctuation = "!#$%&'*+-.^_`|~";
    for (size_t i = 0; punctuation[i]; ++i) if (c == static_cast<unsigned char>(punctuation[i])) return true;
    return false;
}
}

error parse_url(const char* s, size_t n, url& out) {
    out = url{};
    if (!s || n == 0) return error::invalid;
    if (n > max_url) return error::too_large;
    if (!safe_reference(s, n)) return error::invalid;
    if (!starts(s, n, "http://")) return error::unsupported;
    size_t end = 7;
    while (end < n && s[end] != '/' && s[end] != '?' && s[end] != '#') ++end;
    size_t host_end = 7;
    while (host_end < end && s[host_end] != ':') ++host_end;
    const size_t host_size = host_end - 7;
    if (!host_size || host_size > 253) return error::invalid;
    // ASCII DNS reg-name / dotted IPv4 only. No credentials, IPv6, IDNA or escapes.
    size_t label = 0;
    for (size_t i = 7; i < host_end; ++i) {
        const char c = lower(s[i]);
        if (c == '.') {
            if (!label || s[i - 1] == '-') return error::invalid;
            label = 0;
        } else {
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) return error::invalid;
            if ((!label && c == '-') || ++label > 63) return error::invalid;
        }
        out.host[i - 7] = c;
    }
    if (!label || s[host_end - 1] == '-') return error::invalid;
    out.host[host_size] = 0;
    if (host_end != end) {
        unsigned port = 0;
        if (++host_end == end) return error::invalid;
        for (size_t i = host_end; i < end; ++i) {
            if (s[i] < '0' || s[i] > '9') return error::invalid;
            port = port * 10 + unsigned(s[i] - '0');
            if (port > 65535) return error::invalid;
        }
        if (!port) return error::invalid;
        out.port = static_cast<uint16_t>(port);
    }
    return target(s + end, n - end, out.target);
}

error resolve(const url& base, const char* s, size_t n, url& out) {
    if (!s) return error::invalid;
    if (n > max_url) return error::too_large;
    if (!safe_reference(s, n)) return error::invalid;
    if (starts(s, n, "http://") || starts(s, n, "https://")) return parse_url(s, n, out);
    if (n >= 2 && s[0] == '/' && s[1] == '/') {
        char absolute[max_url + 1];
        if (n + 5 > max_url) return error::too_large;
        copy(absolute, sizeof absolute, "http:", 5);
        copy(absolute + 5, sizeof absolute - 5, s, n);
        return parse_url(absolute, n + 5, out);
    }
    size_t first = 0;
    while (first < n && s[first] != '/' && s[first] != '?' && s[first] != '#') {
        if (s[first] == ':') return error::unsupported;
        ++first;
    }
    out = base;
    if (!n || s[0] == '#') return error::ok;
    if (s[0] == '/') return target(s, n, out.target);
    char merged[max_url + 1];
    size_t prefix = length(base.target, sizeof base.target);
    if (prefix > max_url) return error::invalid;
    for (size_t i = 0; i < prefix; ++i) if (base.target[i] == '?') { prefix = i; break; }
    if (s[0] != '?') while (prefix && base.target[prefix - 1] != '/') --prefix;
    if (prefix + n > max_url) return error::too_large;
    copy(merged, sizeof merged, base.target, prefix);
    copy(merged + prefix, sizeof merged - prefix, s, n);
    return target(merged, prefix + n, out.target);
}

error get_request(const url& u, char* out, size_t cap, size_t& size) {
    size = 0;
    const size_t hn = length(u.host, sizeof u.host), tn = length(u.target, sizeof u.target);
    if (!out || !hn || hn > 253 || !tn || tn > max_url || !u.port) return error::invalid;
    // Revalidate caller-owned structures before emitting headers.
    char absolute[max_url + 300]; size_t a = 0;
    const char* pre = "http://";
    for (size_t i = 0; pre[i]; ++i) absolute[a++] = pre[i];
    for (size_t i = 0; i < hn; ++i) absolute[a++] = u.host[i];
    for (size_t i = 0; i < tn; ++i) absolute[a++] = u.target[i];
    url checked;
    if (parse_url(absolute, a, checked) != error::ok || u.target[0] != '/') return error::invalid;
    const size_t canonical_target_length = length(checked.target, sizeof checked.target);
    auto append = [&](const char* s, size_t n) {
        if (n > cap - size) return false;
        for (size_t i = 0; i < n; ++i) out[size++] = s[i];
        return true;
    };
    if (!append("GET ", 4) || !append(checked.target, canonical_target_length) || !append(" HTTP/1.1\r\nHost: ", 17) || !append(checked.host, hn)) { size = 0; return error::too_large; }
    if (u.port != 80) {
        char digits[6]; size_t n = 0; unsigned port = u.port;
        do { digits[n++] = char('0' + port % 10); port /= 10; } while (port);
        if (!append(":", 1)) { size = 0; return error::too_large; }
        while (n) if (!append(digits + --n, 1)) { size = 0; return error::too_large; }
    }
    const char tail[] = "\r\nConnection: close\r\nAccept-Encoding: identity\r\n\r\n";
    if (!append(tail, sizeof tail - 1)) { size = 0; return error::too_large; }
    return error::ok;
}

error parse_response(const unsigned char* data, size_t n, bool eof, response& out) {
    out = response{};
    if (!data && n) return error::invalid;
    if (n > max_headers + max_body) return error::too_large;
    size_t end = 0;
    const size_t scan = n < max_headers ? n : max_headers;
    for (size_t i = 0; i + 3 < scan; ++i)
        if (data[i] == '\r' && data[i+1] == '\n' && data[i+2] == '\r' && data[i+3] == '\n') { end = i + 4; break; }
    if (!end) return n >= max_headers ? error::too_large : eof ? error::truncated : error::need_more;
    const char* s = reinterpret_cast<const char*>(data);
    if (end < 16 || !(starts(s, 9, "http/1.1 ") || starts(s, 9, "http/1.0 "))) return error::invalid;
    if (s[9] < '1' || s[9] > '5' || s[10] < '0' || s[10] > '9' || s[11] < '0' || s[11] > '9' || s[12] != ' ') return error::invalid;
    out.status = unsigned(s[9] - '0') * 100 + unsigned(s[10] - '0') * 10 + unsigned(s[11] - '0');
    size_t pos = 13;
    while (pos + 1 < end && !(s[pos] == '\r' && s[pos+1] == '\n')) {
        const unsigned c = data[pos++];
        if ((c < 32 && c != 9) || c == 127) return error::invalid;
    }
    pos += 2;
    bool have_length = false, have_location = false;
    size_t body = 0, fields = 0;
    while (pos + 2 < end) {
        if (++fields > 64) return error::too_large;
        size_t colon = pos;
        while (colon < end && token(data[colon])) ++colon;
        if (colon == pos || colon >= end || s[colon] != ':') return error::invalid;
        size_t start = colon + 1, line = start;
        while (line + 1 < end && !(s[line] == '\r' && s[line+1] == '\n')) {
            const unsigned c = data[line++];
            if ((c < 32 && c != 9) || c == 127) return error::invalid;
        }
        size_t stop = line;
        while (start < stop && (s[start] == ' ' || s[start] == '\t')) ++start;
        while (stop > start && (s[stop-1] == ' ' || s[stop-1] == '\t')) --stop;
        if (equal(s + pos, colon - pos, "content-length")) {
            if (have_length || start == stop) return error::invalid;
            have_length = true;
            for (size_t i = start; i < stop; ++i) {
                if (s[i] < '0' || s[i] > '9') return error::invalid;
                const size_t digit = size_t(s[i] - '0');
                if (body > (max_body - digit) / 10) return error::too_large;
                body = body * 10 + digit;
            }
        } else if (equal(s + pos, colon - pos, "transfer-encoding")) return error::unsupported;
        else if (equal(s + pos, colon - pos, "content-encoding")) {
            if (!equal(s + start, stop - start, "identity")) return error::unsupported;
        } else if (equal(s + pos, colon - pos, "location")) {
            if (have_location || !safe_reference(s + start, stop - start)) return error::invalid;
            if (!copy(out.location, sizeof out.location, s + start, stop - start)) return error::too_large;
            have_location = true;
        }
        pos = line + 2;
    }
    if (out.status < 200) return error::unsupported;
    if (out.status == 204 || out.status == 304) {
        // GET 304's Content-Length, if present, is metadata, not a body length.
        if (out.status == 204 && have_length) return error::invalid;
        body = 0;
    } else if (!have_length) return error::unsupported;
    out.body_offset = end; out.body_length = body;
    if (n - end < body) return eof ? error::truncated : error::need_more;
    return n - end == body ? error::ok : error::invalid;
}

bool is_redirect(unsigned status) { return status == 301 || status == 302 || status == 303 || status == 307 || status == 308; }
error redirect(const url& base, const response& value, unsigned& count, url& out) {
    if (!is_redirect(value.status) || !value.location[0]) return error::invalid;
    if (count >= 5) return error::too_large;
    const error result = resolve(base, value.location, length(value.location, sizeof value.location), out);
    if (result == error::ok) ++count;
    return result;
}
const char* error_name(error e) {
    switch (e) {
    case error::ok: return "ok"; case error::need_more: return "need_more";
    case error::invalid: return "invalid"; case error::unsupported: return "unsupported";
    case error::too_large: return "too_large"; case error::truncated: return "truncated";
    }
    return "invalid";
}
}
