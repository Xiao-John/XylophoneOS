// SPDX-License-Identifier: Apache-2.0
#ifndef XYP_NATIVE_C_HEADERS
#define XYP_NATIVE_C_HEADERS 1
#endif
#include "xypm_native.hpp"
#include "../../ports/browser_http/transport.hpp"
#include "../../ports/native_tls/stream.hpp"
#include "../../ports/native_tls/trust_store.hpp"
#include <sys/stat.h>
#include <unistd.h>

namespace {
using namespace xypm_native;
#ifdef XYP_GHCR_FIXTURE_PORT
constexpr xos::u16 registry_port = XYP_GHCR_FIXTURE_PORT;
#else
constexpr xos::u16 registry_port = 443;
#endif
constexpr char registry[] = "ghcr.io";
constexpr char blob_host[] = "pkg-containers.githubusercontent.com";
constexpr char manifest_type[] = "application/vnd.oci.image.manifest.v1+json";
constexpr char package_type[] = "application/vnd.xos.xpk.v1";
constexpr char empty_digest[] = "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a";
unsigned char headers[browser_http::max_headers];
char metadata[max_manifest_bytes];
char token[8193];
size_t metadata_size;

bool token_char(char c) {
    return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
           (c >= '0' && c <= '9') || strchr("._~+/=-", c);
}

bool repository_name(const char* name) {
    if (!*name || strlen(name) > 255 || !strchr(name, '/')) return false;
    bool separator = true;
    for (const char* cursor = name; *cursor; ++cursor) {
        const char c = *cursor;
        if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9')) { separator = false; continue; }
        if (separator || !strchr("/._-", c)) return false;
        separator = true;
    }
    return !separator;
}

bool valid_digest(const char* digest) {
    return !strncmp(digest, "sha256:", 7) && hash_text(digest + 7);
}

bool parse_pin(const char* digest, unsigned char* bytes) {
    if (!hash_text(digest)) return false;
    for (unsigned i = 0; i < 32; ++i) {
        auto hex = [](char digit) { return digit <= '9' ? digit - '0' : digit - 'a' + 10; };
        bytes[i] = static_cast<unsigned char>((hex(digest[2*i]) << 4) | hex(digest[2*i+1]));
    }
    return true;
}

int fail(const char* stage, xos::i64 status = 0) {
    fprintf(stderr, "xypm-ghcr: %s (%lld)\n", stage, static_cast<long long>(status));
    return 3;
}

xos::i64 request(xos::u64 service, xos::u32 ip, const native_tls::trust_store& store,
                 const browser_http::url& url, const char* accept, const char* bearer,
                 browser_http::response_sink sink, void* output, size_t limit,
                 browser_http::response& reply, xos::u64 deadline) {
    char checked[browser_http::max_url + 512];
    size_t checked_length = 0;
    if (url.protocol != browser_http::scheme::https || url.port != registry_port ||
        browser_http::get_request(url, checked, sizeof checked, checked_length) != browser_http::error::ok)
        return xos::net2::invalid;
    char wire[browser_http::max_url + 9000];
    const int count = snprintf(wire, sizeof wire, "GET %s HTTP/1.0\r\nHost: %s\r\n"
        "Connection: close\r\nAccept-Encoding: identity\r\nAccept: %s\r\n%s%s%s\r\n",
        url.target, url.host, accept, bearer ? "Authorization: Bearer " : "",
        bearer ? bearer : "", bearer ? "\r\n" : "");
    if (count < 0 || static_cast<size_t>(count) >= sizeof wire) return xos::net2::invalid;
    native_tls::stream tls;
    auto status = tls.connect(service, ip, url.port, url.host, store, deadline);
    if (status) return status;
    for (size_t offset = 0; offset < static_cast<size_t>(count);) {
        status = tls.write(reinterpret_cast<const unsigned char*>(wire) + offset,
                           static_cast<size_t>(count) - offset);
        if (status <= 0) return status ? status : xos::net2::io;
        offset += static_cast<size_t>(status);
    }
    const auto read = browser_http::read_streamed_response(
        [](void* ctx, unsigned char* buffer, xos::u32 size) -> xos::i64 {
            return static_cast<native_tls::stream*>(ctx)->read(buffer, size);
        }, &tls, sink, output, headers, sizeof headers, limit, reply);
    return read ? read : tls.finish();
}

bool decode_token() {
    jmp_buf recovery;
    error_target = &recovery;
    if (setjmp(recovery)) { error_target = nullptr; return false; }
    auto* value = field(json_parser(metadata, metadata_size).parse(), "token");
    const auto* secret = text(value, "invalid GHCR token", sizeof token - 1);
    require(*secret, "empty GHCR token");
    for (const char* ch = secret; *ch; ++ch) require(token_char(*ch), "invalid GHCR token");
    strcpy(token, secret);
    error_target = nullptr;
    return true;
}

bool verify_manifest_digest(const char* expected) {
    sha256 hash;
    hash.update(metadata, metadata_size);
    unsigned char bytes[32];
    char digest[65];
    hash.finish(bytes);
    hex_digest(bytes, digest);
    return !strcmp(expected + 7, digest);
}

bool decode_manifest(char* blob, size_t& size) {
    jmp_buf recovery;
    error_target = &recovery;
    if (setjmp(recovery)) { error_target = nullptr; return false; }
    auto* manifest = json_parser(metadata, metadata_size).parse();
    const auto equals = [](value* object, const char* key, const char* expected_text) {
        auto* item = field(object, key);
        return item && item->type == kind::string && !strcmp(item->text, expected_text);
    };
    require(unsigned_number(field(manifest, "schemaVersion"), 2, "OCI schema") == 2 &&
            equals(manifest, "mediaType", manifest_type) && equals(manifest, "artifactType", package_type),
            "invalid OCI XPK manifest");
    auto* config = need(manifest, "config", kind::object);
    require(equals(config, "mediaType", "application/vnd.oci.empty.v1+json") &&
            equals(config, "digest", empty_digest) &&
            unsigned_number(field(config, "size"), 2, "OCI config size") == 2, "invalid OCI config");
    auto* layer = need(manifest, "layers", kind::array)->child;
    require(layer && !layer->next && equals(layer, "mediaType", package_type), "expected one XPK layer");
    const auto* pinned = text(field(layer, "digest"), "OCI layer digest", 71);
    require(valid_digest(pinned), "invalid OCI layer digest");
    const auto length = unsigned_number(field(layer, "size"), max_archive_bytes, "OCI layer size");
    require(length && length % 512 == 0, "invalid XPK layer length");
    strcpy(blob, pinned);
    size = static_cast<size_t>(length);
    error_target = nullptr;
    return true;
}

bool verify_download(FILE* file, size_t size, const char* digest) {
    jmp_buf recovery;
    error_target = &recovery;
    if (setjmp(recovery)) { error_target = nullptr; return false; }
    const auto verified = verify_package(file, size);
    error_target = nullptr;
    return !strcmp(verified.digest, digest + 7);
}
}

int xypm_ghcr_fetch(int argc, char** argv) {
    if (argc != 10) {
        fputs("usage: xypm-ghcr NET_PID GHCR_IP BLOB_IP CA_FILE CA_GENERATION CA_SHA256 OWNER/NAME MANIFEST_DIGEST NEW_DIRECTORY\n", stderr);
        return 2;
    }
    char* end = nullptr;
    const auto service = strtoull(argv[1], &end, 10);
    if (!service || *end) return fail("invalid network service PID");
    xos::u32 registry_ip = 0, blob_ip = 0;
    native_tls::trust_store_pin pin;
    pin.generation = strtoull(argv[5], &end, 10);
    if (!pin.generation || *end || !parse_pin(argv[6], pin.sha256) ||
        !xos::net2::parse_ipv4(argv[2], registry_ip) || !xos::net2::parse_ipv4(argv[3], blob_ip) ||
        !repository_name(argv[7]) || !valid_digest(argv[8]) || argv[9][0] != '/' ||
        strlen(argv[9]) > 220) return fail("invalid configuration");
    native_tls::trust_store trust;
    const auto ca_status = trust.load_file(argv[4], pin);
    if (ca_status != native_tls::trust_store_result::ok) return fail("trust store", static_cast<int>(ca_status));
    const auto now = xos::sdk::syscall(xos::sys_clock_monotonic);
    if (now < 0) return fail("monotonic clock", now);
    const auto deadline = static_cast<xos::u64>(now) + 600'000'000'000ull;
    browser_http::url target{};
    target.protocol = browser_http::scheme::https;
    target.port = registry_port;
    strcpy(target.host, registry);
    browser_http::response reply{};
    const auto collect = [](void*, const unsigned char* bytes, xos::u32 size) -> xos::i64 {
        if (size > sizeof metadata - metadata_size) return xos::net2::resources;
        memcpy(metadata + metadata_size, bytes, size);
        metadata_size += size;
        return size;
    };
    snprintf(target.target, sizeof target.target, "/token?service=ghcr.io&scope=repository:%s:pull", argv[7]);
    auto status = request(service, registry_ip, trust, target, "application/json", nullptr,
                          collect, nullptr, sizeof metadata, reply, deadline);
    if (status || reply.status != 200 || !decode_token())
        return fail("GHCR anonymous token", status ? status : reply.status);
    puts("XYP_GHCR_TOKEN_OK");

    metadata_size = 0;
    snprintf(target.target, sizeof target.target, "/v2/%s/manifests/%s", argv[7], argv[8]);
    status = request(service, registry_ip, trust, target, manifest_type, token,
                     collect, nullptr, sizeof metadata, reply, deadline);
    char digest[72];
    size_t size = 0;
    if (status || reply.status != 200) return fail("GHCR manifest", status ? status : reply.status);
    if (!verify_manifest_digest(argv[8])) return fail("GHCR manifest digest mismatch");
    if (!decode_manifest(digest, size)) return fail("OCI manifest is not an XPK artifact");

    if (mkdir(argv[9], 0700)) return fail("create new output directory");
    char stage[256], output[256];
    snprintf(stage, sizeof stage, "%s/package.part", argv[9]);
    snprintf(output, sizeof output, "%s/package.xpk", argv[9]);
    FILE* file = fopen(stage, "w+bx");
    if (!file) { (void)rmdir(argv[9]); return fail("create temporary XPK"); }

    auto discard = [&]() {
        (void)fclose(file);
        (void)unlink(stage);
        (void)rmdir(argv[9]);
    };
    const auto write = [](void* ctx, const unsigned char* bytes, xos::u32 count) -> xos::i64 {
        return fwrite(bytes, 1, count, static_cast<FILE*>(ctx)) == count ? count : xos::net2::io;
    };
    snprintf(target.target, sizeof target.target, "/v2/%s/blobs/%s", argv[7], digest);
    status = request(service, registry_ip, trust, target, "application/octet-stream", token,
                     write, file, size, reply, deadline);
    if (!status && browser_http::is_redirect(reply.status)) {
        browser_http::url destination{};
        unsigned redirects = 0;
        if (reply.body_length || browser_http::redirect(target, reply, redirects, destination) != browser_http::error::ok ||
            strcmp(destination.host, blob_host)) { discard(); return fail("invalid blob redirect"); }
        status = request(service, blob_ip, trust, destination, "application/octet-stream", nullptr,
                         write, file, size, reply, deadline);
    }
    if (status || reply.status != 200 || reply.body_length != size || fflush(file) ||
        !verify_download(file, size, digest)) { discard(); return fail("download or XPK verification", status); }
    if (fclose(file) || rename(stage, output)) {
        (void)unlink(stage);
        (void)rmdir(argv[9]);
        return fail("publish verified XPK");
    }
    printf("XYP_GHCR_VERIFIED path=%s sha256=%s\n", output, digest + 7);
    return 0;
}

#ifndef XYP_GHCR_LINKED
int main(int argc, char** argv) { return xypm_ghcr_fetch(argc, argv); }
#endif
