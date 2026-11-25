// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "content.hpp"
#include "network_policy.hpp"
#include "../browser_http/transport.hpp"
#include <QtCore/QCryptographicHash>
#include <cstdio>

namespace browser {
inline bool remote(const QString& location) {
    return location.startsWith(QStringLiteral("http://"), Qt::CaseInsensitive);
}
inline QString display_location(const QString& location) {
    return remote(location) ? location : QStringLiteral("file:") + location;
}
inline QString resolve_location(const QString& value, const QString& base, bool resource = false) {
    if (resource && !remote(base) && remote(value)) return {};
    if (value.startsWith(QStringLiteral("file:")))
        return resource && remote(base) ? QString{} : resolve(value, QStringLiteral("/web/start.html"));
    if (!remote(value) && !remote(base)) return resolve(value, base);
    const auto bytes = value.toUtf8();
    browser_http::url base_url{}, resolved{};
    const browser_http::url* relative_to = nullptr;
    if (remote(base)) {
        const auto encoded = base.toUtf8();
        if (browser_http::parse_url(encoded.constData(), static_cast<size_t>(encoded.size()), base_url) != browser_http::error::ok) return {};
        relative_to = &base_url;
    }
    if (remote_location(bytes.constData(), static_cast<size_t>(bytes.size()), relative_to, resource, resolved) != browser_http::error::ok) return {};
    char formatted[browser_http::max_url + 1]{};
    return format_location(resolved, formatted, sizeof(formatted)) ? QString::fromLatin1(formatted) : QString{};
}
inline bool resource_extension(const QString& location, const char* suffix) {
    return location.section('?', 0, 0).endsWith(QString::fromLatin1(suffix));
}
inline QString resolve_resource(const QString& value, const QString& base, const QString& document) {
    if (!remote(document)) {
        return remote(base) ? QString{} : resolve_location(value, base, true);
    }
    if (!remote(base)) return {};
    const auto document_bytes = document.toUtf8(), base_bytes = base.toUtf8(), reference = value.toUtf8();
    browser_http::url page{}, relative_to{}, result{};
    if (browser_http::parse_url(document_bytes.constData(), static_cast<size_t>(document_bytes.size()), page) != browser_http::error::ok ||
        browser_http::parse_url(base_bytes.constData(), static_cast<size_t>(base_bytes.size()), relative_to) != browser_http::error::ok ||
        remote_resource_location(reference.constData(), static_cast<size_t>(reference.size()), page, relative_to, result) != browser_http::error::ok) return {};
    char formatted[browser_http::max_url + 1]{};
    return format_location(result, formatted, sizeof(formatted)) ? QString::fromLatin1(formatted) : QString{};
}

class content_source {
    xos::u64 service_pid_;
    xos::net2::client network_;
    navigation_budget budget_{};
    bool connected_ = false, finished_ = false;
public:
    explicit content_source(xos::u64 service_pid = 0) : service_pid_(service_pid) {}
    ~content_source() { finish(); }
    content_source(const content_source&) = delete;
    content_source& operator=(const content_source&) = delete;
    void begin() { finish(); finished_ = false; budget_ = {}; }
    void finish() { network_.close(); connected_ = false; finished_ = true; }
    bool load(QString& location, QByteArray& bytes, int limit, QString& error) {
        if (!remote(location)) return read(location, bytes, limit, error);
        bytes.clear();
        if (!service_pid_) { error = QStringLiteral("Start with --network-service-pid to use HTTP"); return false; }
        if (finished_) { error = QStringLiteral("Resource was not loaded during navigation"); return false; }
        const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
        if ((!budget_.deadline && !budget_.begin(now)) || !budget_.request(now)) {
            error = QStringLiteral("Navigation time or request budget exceeded"); return false;
        }
        if (limit < 0 || budget_.remaining_bytes() <= browser_http::max_headers + 1) {
            error = QStringLiteral("Navigation byte budget exceeded"); return false;
        }
        const size_t body_limit = static_cast<size_t>(limit) < browser_http::max_body
            ? static_cast<size_t>(limit) : browser_http::max_body;
        const size_t wanted = browser_http::max_headers + body_limit;
        const size_t capacity = wanted < budget_.remaining_bytes() - 1
            ? wanted : budget_.remaining_bytes() - 1;
        // Reserve before I/O. Malformed optional resources spend their whole
        // reservation, even when the transport cannot report a partial length.
        const size_t reservation = capacity + 1;
        if (!budget_.consume(reservation)) { error = QStringLiteral("Navigation byte budget exceeded"); return false; }
        if (!connected_) {
            const auto result = network_.connect(service_pid_);
            if (result) { error = QStringLiteral("Network service unavailable (%1)").arg(static_cast<qlonglong>(result)); return false; }
            connected_ = true;
        }
        const auto encoded = location.toUtf8();
        browser_http::url requested{}, final_url{};
        if (remote_location(encoded.constData(), static_cast<size_t>(encoded.size()), nullptr, false, requested) != browser_http::error::ok) {
            error = QStringLiteral("Only numeric IPv4 HTTP addresses are available"); return false;
        }
        QByteArray response_bytes;
        response_bytes.resize(static_cast<qsizetype>(capacity));
        browser_http::response response{};
        // One request per resource makes the document-wide request budget exact.
        const auto result = browser_http::fetch(network_, requested,
            reinterpret_cast<xos::u8*>(response_bytes.data()), capacity,
            budget_.deadline, response, final_url, 0);
        if (result) { error = QStringLiteral("HTTP request failed (%1)").arg(static_cast<qlonglong>(result)); return false; }
        if (response.body_offset > capacity || response.body_length > capacity - response.body_offset ||
            response.body_length > body_limit) { error = QStringLiteral("HTTP response exceeds resource budget"); return false; }
        const size_t received = response.body_offset + response.body_length;
        budget_.bytes -= reservation - received;
        if (response.status < 200 || response.status >= 300) {
            error = QStringLiteral("HTTP status %1; redirects are not followed").arg(response.status); return false;
        }
        char formatted[browser_http::max_url + 1]{};
        if (!same_origin(requested, final_url) || !format_location(final_url, formatted, sizeof(formatted))) {
            error = QStringLiteral("HTTP response origin rejected"); return false;
        }
        location = QString::fromLatin1(formatted);
        bytes = response_bytes.mid(static_cast<qsizetype>(response.body_offset), static_cast<qsizetype>(response.body_length));
        const auto digest = QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex();
        std::printf("BROWSER_HTTP status=%u bytes=%lld sha256=%s\n", response.status,
                    static_cast<long long>(bytes.size()), digest.constData());
        return true;
    }
};
}
