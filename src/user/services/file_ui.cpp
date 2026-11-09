// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/file_ui.hpp>
#include <xos/file_client.hpp>
#include <xos/fault_sha256.hpp>
#include <xos/sdk.hpp>
#include <xos/text.hpp>

namespace xos::ui {
namespace {
using namespace xos;
using namespace xos::sdk;

file::client client;
u8 image_buffer[24576];
u8 dash_buffer[file::request_data_size];
u8 editor_buffer[8192];
u32 editor_length;
constexpr u32 max_staged_packages = 16;
char staged_packages[max_staged_packages][160];
u32 staged_package_count = 0;
bool boot_payload_installed = false;
const char* bundle_marker_path = "/var/cache/xypm/du4_bundle.installed";

void print_bytes(const u8* data, u32 length) {
    u32 offset = 0;
    while (offset < length) {
        u32 chunk = length - offset;
        if (chunk > 256) { chunk = 256; }
        const i64 sent = write(1, data + offset, chunk);
        if (sent <= 0) { return; }
        offset += static_cast<u32>(sent);
    }
}

void error_line(const char* operation, i64 result) {
    print("[files] "); print(operation); print(" error="); signed_decimal(result); print("\n");
}

bool read_image(const char* name, u8* buffer, u32 capacity, u32& length) {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { return false; }
        if (!equal(name, info.name)) { continue; }
        if (info.size > capacity) { return false; }
        image_read_request request{0, reinterpret_cast<u64>(buffer), info.size};
        const i64 result = syscall(sys_image_read, id, reinterpret_cast<u64>(&request));
        if (result != static_cast<i64>(info.size)) { return false; }
        length = static_cast<u32>(info.size);
        return true;
    }
    return false;
}

void save_editor(const char* name, bool& dirty) {
    const i64 result = client.replace(name, editor_buffer, editor_length);
    if (result != 0) {
        error_line("save", result);
        print("[edit] buffer retained; result may be unknown, reread file before retry\n");
        return;
    }
    dirty = false;
    print("[edit] saved "); print(name); print(" bytes="); decimal(editor_length); print("\n");
}

void editor_help() {
    print("[edit] text lines append; :: starts a literal ':' line\n"
          "[edit] :w save  :wq save+quit  :q quit  :q! discard  :p [N [M]] print\n"
          "[edit] :i N insert before  :r N replace  :d N delete  :c clear  :help\n");
}

// A line includes its terminating LF, if present. CR and all other bytes are content.
u32 editor_lines() {
    u32 count = 0;
    for (u32 i = 0; i < editor_length; ++i) {
        if (editor_buffer[i] == '\n') { ++count; }
    }
    if (editor_length && editor_buffer[editor_length - 1] != '\n') { ++count; }
    return count;
}

bool editor_line_range(u32 number, u32& start, u32& end) {
    if (!number) { return false; }
    u32 current = 1;
    start = 0;
    while (start < editor_length && current < number) {
        if (editor_buffer[start++] == '\n') { ++current; }
    }
    if (current != number || start >= editor_length) { return false; }
    end = start;
    while (end < editor_length && editor_buffer[end] != '\n') { ++end; }
    if (end < editor_length) { ++end; }
    return true;
}

// Only safe printable UTF-8 reaches the terminal. Controls and malformed bytes
// are rendered as hexadecimal, never interpreted as terminal commands.
void editor_print_range(u32 start, u32 end) {
    static const char hex[] = "0123456789ABCDEF";
    for (u32 i = start; i < end;) {
        const u8 ch = editor_buffer[i];
        if (ch == '\n') { print("\n"); ++i; continue; }
        xos::text::decoded unit{};
        const auto status = xos::text::decode(reinterpret_cast<const char*>(editor_buffer + i), end - i, unit);
        if (status == xos::text::decode_status::ok && unit.codepoint >= 0x20 &&
            !(unit.codepoint >= 0x7f && unit.codepoint <= 0x9f)) {
            print_bytes(editor_buffer + i, unit.bytes);
            i += unit.bytes;
        } else {
            char escaped[] = {'\\', 'x', hex[ch >> 4], hex[ch & 15]};
            (void)write(1, escaped, sizeof(escaped));
            ++i;
        }
    }
}

bool editor_number(const char*& p, u32& value) {
    while (*p == ' ') { ++p; }
    if (*p < '0' || *p > '9') { return false; }
    value = 0;
    do {
        const u32 digit = static_cast<u32>(*p++ - '0');
        if (value > (0xffffffffu - digit) / 10u) { return false; }
        value = value * 10u + digit;
    } while (*p >= '0' && *p <= '9');
    return true;
}

bool editor_end(const char* p) {
    while (*p == ' ') { ++p; }
    return *p == '\0';
}

// Returns false for an entire rejected input; no caller mutates the buffer.
bool editor_read_line(char* line, u32& used, bool& last_cr) {
    used = 0;
    u32 echoed = 0;
    bool invalid = false;
    bool overflow = false;
    for (;;) {
        char byte = 0;
        const i64 got = read(0, &byte, 1);
        if (got <= 0) { yield(); continue; }
        if (byte == '\n' && last_cr) { last_cr = false; continue; }
        last_cr = byte == '\r';
        if (byte == '\r' || byte == '\n') { print("\n"); break; }
        const u8 value = static_cast<u8>(byte);
        if (value == '\b' || value == 127) {
            if (used && !overflow && !invalid) {
                const auto erased = text::erase_last(line, used);
                used = erased.size;
                if (echoed > used) { echoed = used; }
                for (u32 i = 0; i < erased.columns; ++i) { print("\b \b"); }
            }
        } else if ((value >= 32 && value <= 126) || value >= 0x80) {
            if (used < 159 && !overflow && !invalid) {
                line[used++] = byte;
                text::decoded unit{};
                const auto status = text::decode(line + echoed, used - echoed, unit);
                if (status == text::decode_status::invalid ||
                    (status == text::decode_status::ok && unit.codepoint >= 0x7f && unit.codepoint <= 0x9f)) {
                    invalid = true;
                } else if (status == text::decode_status::ok) {
                    (void)write(1, line + echoed, unit.bytes);
                    echoed += unit.bytes;
                }
            } else { overflow = true; }
        } else { invalid = true; }
    }
    line[used] = '\0';
    if (overflow) { print("[edit] line too long; discarded\n"); return false; }
    if (invalid || !text::valid(line, used)) {
        print("[edit] invalid input; discarded\n"); return false;
    }
    // C1 controls are legal UTF-8 but must not reach the document via input.
    for (u32 i = 0; i < used;) {
        text::decoded unit{};
        (void)text::decode(line + i, used - i, unit);
        if (unit.codepoint >= 0x7f && unit.codepoint <= 0x9f) {
            print("[edit] invalid input; discarded\n"); return false;
        }
        i += unit.bytes;
    }
    return true;
}

bool editor_replace_range(u32 start, u32 end, const char* data, u32 length, bool newline) {
    const u32 removed = end - start;
    const u32 added = length + (newline ? 1u : 0u);
    if (added > sizeof(editor_buffer) - (editor_length - removed)) {
        print("[edit] buffer full; line rejected, buffer retained\n"); return false;
    }
    if (added > removed) {
        for (u32 i = editor_length; i > end; --i) { editor_buffer[i + added - removed - 1] = editor_buffer[i - 1]; }
    } else if (added < removed) {
        for (u32 i = end; i < editor_length; ++i) { editor_buffer[i - removed + added] = editor_buffer[i]; }
    }
    for (u32 i = 0; i < length; ++i) { editor_buffer[start + i] = static_cast<u8>(data[i]); }
    if (newline) { editor_buffer[start + length] = '\n'; }
    editor_length = editor_length - removed + added;
    return true;
}

void run_editor(const char* name) {
    u32 loaded = 0;
    i64 result = client.read_all(name, editor_buffer, sizeof(editor_buffer), loaded);
    if (result != 0) {
        if (result != static_cast<i64>(file::status::not_found)) {
            error_line("open", result);
            return;
        }
        loaded = 0;
    }
    editor_length = loaded;
    const bool existed = result == 0;
    bool dirty = false;
    bool last_cr = false;
    print("[edit] "); print(name); print(" bytes="); decimal(editor_length);
    print(existed ? " (loaded)\n" : " (new)\n");
    editor_help();
    for (;;) {
        print("| ");
        char line[160]{};
        u32 used = 0;
        if (!editor_read_line(line, used, last_cr)) { continue; }
        if (line[0] == ':' && line[1] != ':') {
            if (equal(line, ":w") || equal(line, ":wq")) {
                // A failed save of a clean buffer must not make :wq exit.
                bool save_pending = true;
                save_editor(name, save_pending);
                if (!save_pending) { dirty = false; }
                if (equal(line, ":wq") && !save_pending) { return; }
            } else if (equal(line, ":q")) {
                if (dirty) { print("[edit] unsaved changes; use :w or :q!\n"); }
                else { return; }
            } else if (equal(line, ":q!")) {
                return;
            } else if (line[1] == 'p' && (line[2] == '\0' || line[2] == ' ')) {
                const char* p = line + 2;
                u32 first = 1, last = editor_lines();
                if (!editor_end(p)) {
                    if (!editor_number(p, first)) { print("[edit] invalid range\n"); continue; }
                    last = first;
                    if (!editor_end(p) && !editor_number(p, last)) { print("[edit] invalid range\n"); continue; }
                    if (!editor_end(p) || !first || first > last || last > editor_lines()) {
                        print("[edit] invalid range\n"); continue;
                    }
                }
                if (line[2] == '\0') {
                    editor_print_range(0, editor_length);
                    if (editor_length && editor_buffer[editor_length - 1] != '\n') { print("\n"); }
                } else {
                    for (u32 n = first; n <= last; ++n) {
                        u32 start = 0, end = 0; (void)editor_line_range(n, start, end);
                        decimal(n); print(": "); editor_print_range(start, end);
                        if (end == start || editor_buffer[end - 1] != '\n') { print("\n"); }
                    }
                }
            } else if ((line[1] == 'i' || line[1] == 'r' || line[1] == 'd') && line[2] == ' ') {
                const char operation = line[1];
                const char* p = line + 2;
                u32 number = 0, start = 0, end = 0;
                if (!editor_number(p, number) || !editor_end(p) || !number ||
                    (operation == 'i' && number > editor_lines() + 1) ||
                    (operation != 'i' && !editor_line_range(number, start, end))) {
                    print("[edit] invalid line number\n"); continue;
                }
                if (operation == 'i') {
                    if (number == editor_lines() + 1) { start = end = editor_length; }
                    else { (void)editor_line_range(number, start, end); end = start; }
                }
                if (operation == 'd') {
                    if (editor_replace_range(start, end, "", 0, false)) { dirty = true; }
                    continue;
                }
                print("text| ");
                char replacement[160]{}; u32 length = 0;
                if (!editor_read_line(replacement, length, last_cr)) { continue; }
                const bool terminated = operation == 'i' || (end > start && editor_buffer[end - 1] == '\n');
                // Appending after a non-LF final line needs a separate separator.
                if (operation == 'i' && start == editor_length && editor_length && editor_buffer[editor_length - 1] != '\n') {
                    if (editor_length + 1u + length + 1u > sizeof(editor_buffer)) {
                        print("[edit] buffer full; line rejected, buffer retained\n"); continue;
                    }
                    editor_buffer[editor_length++] = '\n'; ++start; ++end;
                }
                if (editor_replace_range(start, end, replacement, length, terminated)) { dirty = true; }
            } else if (equal(line, ":c")) {
                editor_length = 0; dirty = true; print("[edit] buffer cleared\n");
            } else if (equal(line, ":help")) { editor_help(); }
            else { print("[edit] unknown command; :help\n"); }
            continue;
        }
        const char* content = line;
        if (line[0] == ':' && line[1] == ':') { ++content; --used; }
        const bool separator = editor_length && editor_buffer[editor_length - 1] != '\n';
        if (editor_length + (separator ? 1u : 0u) + used + 1u > sizeof(editor_buffer)) {
            print("[edit] buffer full; line rejected, buffer retained\n"); continue;
        }
        if (separator) { editor_buffer[editor_length++] = '\n'; }
        if (editor_replace_range(editor_length, editor_length, content, used, true)) { dirty = true; }
    }
}
}

// --- XOSBND1 boot bundle (docs/contracts/xos_bundle_v1.md) ---
constexpr u32 bundle_header_size = 64;
constexpr u32 bundle_entry_size = 64;
constexpr u32 bundle_max_members = 16;
struct bundle_entry {
    u32 type;
    u32 name_off;
    u32 name_len;
    u32 reserved;
    u64 data_off;
    u64 data_len;
    u8 sha256[32];
};

bool boot_payload_is_bundle(u64 size) {
    if (size < 8) { return false; }
    u8 magic[8] = {};
    if (syscall(sys_boot_payload, 0, reinterpret_cast<u64>(magic), 8) != 8) { return false; }
    return magic[0]=='X' && magic[1]=='O' && magic[2]=='S' && magic[3]=='B' &&
           magic[4]=='N' && magic[5]=='D' && magic[6]=='1' && magic[7]==0;
}

bool read_payload(u64 offset, void* dst, u32 length) {
    u8* out = static_cast<u8*>(dst);
    u32 done = 0;
    while (done < length) {
        u32 chunk = length - done;
        if (chunk > sizeof(dash_buffer)) { chunk = sizeof(dash_buffer); }
        const i64 got = syscall(sys_boot_payload, offset + done,
                                reinterpret_cast<u64>(dash_buffer), chunk);
        if (got != static_cast<i64>(chunk)) { return false; }
        for (u32 i = 0; i < chunk; ++i) { out[done + i] = dash_buffer[i]; }
        done += chunk;
    }
    return true;
}

char bundle_upper(char value) {
    return value >= 'a' && value <= 'z' ? static_cast<char>(value - 'a' + 'A') : value;
}

bool bundle_name_equal(const char* left, const char* right) {
    u32 i = 0;
    while (left[i] != '\0' && right[i] != '\0') {
        if (bundle_upper(left[i]) != bundle_upper(right[i])) { return false; }
        ++i;
    }
    return left[i] == '\0' && right[i] == '\0';
}

// A member name is one FAT filename: type 5 installs it under /usr/bin, and
// type 2/3/4 stage it under incoming. Backslash and the FAT metacharacters are
// therefore path separators/illegal, not merely diagnostics.
bool valid_bundle_name(const char* name) {
    u32 length = 0;
    while (name[length] != '\0') {
        if (length >= 127) { return false; }
        ++length;
    }
    if (length == 0) { return false; }
    for (u32 i = 0; i < length; ++i) {
        const u8 c = static_cast<u8>(name[i]);
        if (c < 0x20 || c > 0x7e) { return false; }
        if (c == '/' || c == '\\' || c == ':' || c == '*' || c == '?' ||
            c == '"' || c == '<' || c == '>' || c == '|') { return false; }
    }
    if ((length == 1 && name[0] == '.') ||
        (length == 2 && name[0] == '.' && name[1] == '.')) { return false; }
    if (name[length - 1] == '.' || name[length - 1] == ' ') { return false; }
    u32 base_length = 0;
    while (base_length < length && name[base_length] != '.') { ++base_length; }
    const char b0 = bundle_upper(name[0]);
    if (base_length == 3) {
        const char b1 = bundle_upper(name[1]), b2 = bundle_upper(name[2]);
        if ((b0=='C'&&b1=='O'&&b2=='N') || (b0=='P'&&b1=='R'&&b2=='N') ||
            (b0=='A'&&b1=='U'&&b2=='X') || (b0=='N'&&b1=='U'&&b2=='L')) { return false; }
    }
    if (base_length == 4) {
        const char b1 = bundle_upper(name[1]), b2 = bundle_upper(name[2]);
        const char b3 = name[3];
        if (b0=='C' && b1=='O' && b2=='M' && b3 >= '1' && b3 <= '9') { return false; }
        if (b0=='L' && b1=='P' && b2=='T' && b3 >= '1' && b3 <= '9') { return false; }
    }
    return true;
}

bool member_magic_ok(const bundle_entry& entry) {
    u8 magic[6]{};
    if (entry.type == 1 || entry.type == 5) {
        if (entry.data_len < 4) { return false; }
        if (!read_payload(entry.data_off, magic, 4)) { return false; }
        return magic[0] == 0x7f && magic[1] == 'E' && magic[2] == 'L' && magic[3] == 'F';
    }
    if (entry.data_len < 263) { return false; }
    if (!read_payload(entry.data_off + 257, magic, 6)) { return false; }
    return magic[0] == 'u' && magic[1] == 's' && magic[2] == 't' &&
           magic[3] == 'a' && magic[4] == 'r' && magic[5] == 0;
}

bool payload_is_zero(u64 offset, u64 length) {
    u8 scratch[512];
    while (length != 0) {
        const u32 chunk = length > sizeof(scratch) ? static_cast<u32>(sizeof(scratch))
                                                   : static_cast<u32>(length);
        if (!read_payload(offset, scratch, chunk)) { return false; }
        for (u32 i = 0; i < chunk; ++i) { if (scratch[i] != 0) { return false; } }
        offset += chunk;
        length -= chunk;
    }
    return true;
}

bool payload_digest(u8 digest[32]) {
    const i64 size = syscall(sys_boot_payload, 0, 0, 0);
    if (size <= 0) { return false; }
    sha256 hash;
    u64 offset = 0;
    while (offset < static_cast<u64>(size)) {
        u32 chunk = static_cast<u32>(static_cast<u64>(size) - offset);
        if (chunk > sizeof(dash_buffer)) { chunk = sizeof(dash_buffer); }
        if (!read_payload(offset, dash_buffer, chunk)) { return false; }
        hash.update(dash_buffer, chunk);
        offset += chunk;
    }
    hash.finish(digest);
    return true;
}

void digest_text(const u8 digest[32], char output[65]) {
    static const char digits[] = "0123456789abcdef";
    for (u32 i = 0; i < 32; ++i) {
        output[i * 2] = digits[digest[i] >> 4];
        output[i * 2 + 1] = digits[digest[i] & 0x0f];
    }
    output[64] = '\0';
}

bool member_digest_ok(const bundle_entry& entry) {
    sha256 hash;
    u64 offset = 0;
    while (offset < entry.data_len) {
        u32 chunk = static_cast<u32>(entry.data_len - offset);
        if (chunk > sizeof(dash_buffer)) { chunk = sizeof(dash_buffer); }
        if (!read_payload(entry.data_off + offset, dash_buffer, chunk)) { return false; }
        hash.update(dash_buffer, chunk);
        offset += chunk;
    }
    u8 got[32];
    hash.finish(got);
    for (u32 i = 0; i < 32; ++i) { if (got[i] != entry.sha256[i]) { return false; } }
    return true;
}

// Write one member to an absolute path; refuses overwrite of a different existing file.
// base is the member's data_off inside the boot payload (0 for legacy whole-payload ELF).
bool install_member_file(const char* path, u64 length, const u8 want_sha[32], u64 base) {
    u32 existing = 0;
    u32 version = 0;
    const i64 st = client.stat(path, existing, version);
    if (st == 0) {
        if (existing != length) {
            print("[files] bundle conflict: "); print(path); print(" size\n");
            return false;
        }
        if (want_sha == nullptr) {
            print("[files] already present: "); print(path); print("\n");
            return true;
        }
        // Hash the file that is actually on disk, not the boot-payload copy:
        // comparing the payload with its own digest would accept any same-size
        // replacement silently.
        u32 handle = 0;
        u32 opened_size = 0;
        u32 opened_version = 0;
        const i64 opened = client.open(path, xos::file::read_only, handle,
                                       opened_size, opened_version);
        if (opened != 0 || opened_size != length) {
            if (opened == 0) { (void)client.close(handle); }
            print("[files] bundle conflict: "); print(path); print(" digest\n");
            return false;
        }
        sha256 hash;
        u64 offset = 0;
        bool read_ok = true;
        while (offset < length) {
            u32 count = static_cast<u32>(length - offset);
            if (count > sizeof(dash_buffer)) { count = sizeof(dash_buffer); }
            const i64 got_bytes = client.read(handle, dash_buffer, count);
            if (got_bytes <= 0) { read_ok = false; break; }
            hash.update(dash_buffer, static_cast<u32>(got_bytes));
            offset += static_cast<u64>(got_bytes);
        }
        (void)client.close(handle);
        if (!read_ok || offset != length) {
            print("[files] bundle conflict: "); print(path); print(" digest\n");
            return false;
        }
        u8 got[32];
        hash.finish(got);
        for (u32 i = 0; i < 32; ++i) {
            if (got[i] != want_sha[i]) {
                print("[files] bundle conflict: "); print(path); print(" digest\n");
                return false;
            }
        }
        print("[files] bundle already present: "); print(path); print("\n");
        return true;
    }
    if (st != static_cast<i64>(file::status::not_found)) {
        error_line("bundle-stat", st);
        return false;
    }
    i64 result = client.begin_replace(path, static_cast<u32>(length));
    if (result != 0) { error_line("bundle-stage", result); return false; }
    sha256 hash;
    u64 offset = 0;
    while (offset < length) {
        u32 count = static_cast<u32>(length - offset);
        if (count > sizeof(dash_buffer)) { count = sizeof(dash_buffer); }
        if (!read_payload(base + offset, dash_buffer, count)) {
            (void)client.abort_replace();
            return false;
        }
        hash.update(dash_buffer, count);
        result = client.chunk_replace(static_cast<u32>(offset), dash_buffer, count);
        if (result != 0) { break; }
        offset += count;
    }
    u8 got[32];
    hash.finish(got);
    if (result == 0 && want_sha != nullptr) {
        for (u32 i = 0; i < 32; ++i) {
            if (got[i] != want_sha[i]) {
                print("[files] bundle digest mismatch: "); print(path); print("\n");
                result = -1;
                break;
            }
        }
    }
    if (result == 0) { result = client.commit_replace(); }
    if (result != 0) {
        (void)client.abort_replace();
        error_line("bundle-write", result);
        return false;
    }
    if (want_sha == nullptr) {
        // Legacy raw-ELF install path: keep the historical probe string.
        print("[files] dash installed bytes=");
        decimal(static_cast<u32>(length));
        print("\n");
    } else {
        print("[files] bundle installed: ");
        print(path);
        print("\n");
    }
    return true;
}

void install_boot_payload() {
    boot_payload_installed = false;
    const i64 size = syscall(sys_boot_payload, 0, 0, 0);
    if (size <= 0) { boot_payload_installed = true; return; }
    if (static_cast<u64>(size) > 32ull * 1024 * 1024) {
        print("[files] boot payload too large\n");
        return;
    }
    if (!boot_payload_is_bundle(static_cast<u64>(size))) {
        // Only a real ELF may take the legacy raw-dash path; any other bytes
        // would otherwise be persisted as /usr/bin/dash unverified.
        u8 magic[4]{};
        if (static_cast<u64>(size) < sizeof(magic) || !read_payload(0, magic, sizeof(magic)) ||
            magic[0] != 0x7f || magic[1] != 'E' || magic[2] != 'L' || magic[3] != 'F') {
            print("[files] boot payload is not ELF\n");
            return;
        }
        u32 existing = 0;
        u32 version = 0;
        if (client.stat("/usr/bin/dash", existing, version) == 0) {
            boot_payload_installed = true;
            return;
        }
        (void)client.mkdir("/usr");
        (void)client.mkdir("/usr/bin");
        if (!install_member_file("/usr/bin/dash", static_cast<u64>(size), nullptr, 0)) {
            return;
        }
        boot_payload_installed = true;
        return;
    }

    u8 header[bundle_header_size];
    if (!read_payload(0, header, bundle_header_size)) {
        print("[files] bundle header read failed\n");
        return;
    }
    const u32 bundle_version = *reinterpret_cast<const u32*>(header + 8);
    const u32 count = *reinterpret_cast<const u32*>(header + 12);
    const u64 total = *reinterpret_cast<const u64*>(header + 16);
    const u32 names_bytes = *reinterpret_cast<const u32*>(header + 24);
    if (bundle_version != 1 || count < 1 || count > bundle_max_members ||
        total != static_cast<u64>(size) || names_bytes > 2048) {
        print("[files] bundle header rejected\n");
        return;
    }
    for (u32 i = 28; i < bundle_header_size; ++i) {
        if (header[i] != 0) { print("[files] bundle reserved\n"); return; }
    }
    const u64 entries_off = bundle_header_size;
    const u64 entries_end = entries_off + bundle_entry_size * count;
    const u64 names_off = entries_end;
    const u64 names_end = names_off + names_bytes;
    if (names_end > total) { print("[files] bundle truncated\n"); return; }
    u8 names_buf[2048];
    if (names_bytes && !read_payload(names_off, names_buf, names_bytes)) {
        print("[files] bundle names read failed\n");
        return;
    }
    bundle_entry entries[bundle_max_members];
    char member_names[bundle_max_members][128];
    u8 raw[bundle_entry_size];
    u32 dash_count = 0;
    u32 xypm_count = 0;
    u32 daily_count = 0;
    for (u32 i = 0; i < count; ++i) {
        if (!read_payload(entries_off + bundle_entry_size * i, raw, bundle_entry_size)) {
            print("[files] bundle entries read failed\n");
            return;
        }
        bundle_entry& e = entries[i];
        e.type = *reinterpret_cast<const u32*>(raw + 0);
        e.name_off = *reinterpret_cast<const u32*>(raw + 4);
        e.name_len = *reinterpret_cast<const u32*>(raw + 8);
        e.reserved = *reinterpret_cast<const u32*>(raw + 12);
        e.data_off = *reinterpret_cast<const u64*>(raw + 16);
        e.data_len = *reinterpret_cast<const u64*>(raw + 24);
        for (u32 b = 0; b < 32; ++b) { e.sha256[b] = raw[32 + b]; }
        // Range checks use subtraction so a wrapped sum cannot pass them.
        if (e.reserved != 0 || e.name_len < 1 || e.name_len > 127 ||
            e.name_off > names_bytes || e.name_len > names_bytes - e.name_off ||
            e.data_len < 1 || e.data_off < names_end ||
            e.data_off > total || e.data_len > total - e.data_off ||
            (e.data_off & 3u) != 0 || e.type < 1 || e.type > 5) {
            print("[files] bundle entry rejected\n");
            return;
        }
        char* member_name = member_names[i];
        u32 name_used = 0;
        while (name_used < e.name_len && name_used + 1 < 128) {
            const u8 byte = names_buf[e.name_off + name_used];
            // Reject embedded NUL explicitly; C-string validation would silently
            // truncate the declared name and accept a different install target.
            if (byte == 0) { print("[files] bundle bad name\n"); return; }
            member_name[name_used] = static_cast<char>(byte);
            ++name_used;
        }
        member_name[name_used] = 0;
        if (!valid_bundle_name(member_name)) { print("[files] bundle bad name\n"); return; }
        if (e.type == 5 && bundle_name_equal(member_name, "dash")) {
            print("[files] bundle bad tool name\n");
            return;
        }
        for (u32 j = 0; j < i; ++j) {
            if (bundle_name_equal(member_names[j], member_name)) {
                print("[files] bundle duplicate name\n");
                return;
            }
        }
        if (e.type == 1) { ++dash_count; }
        if (e.type == 2) { ++xypm_count; }
        if (e.type == 3) { ++daily_count; }
    }
    // Mirror the host verifier (scripts/xos_bundle.py): the name region must
    // be a compact concatenation, so spans may not overlap or leave gaps or
    // unused tail bytes. count >= 1 is enforced above, so the first span
    // must start at 0.
    u32 name_start[bundle_max_members];
    u32 name_span_len[bundle_max_members];
    for (u32 i = 0; i < count; ++i) {
        name_start[i] = entries[i].name_off;
        name_span_len[i] = entries[i].name_len;
    }
    for (u32 i = 1; i < count; ++i) {
        const u32 start = name_start[i];
        const u32 length = name_span_len[i];
        u32 j = i;
        while (j > 0 && name_start[j - 1] > start) {
            name_start[j] = name_start[j - 1];
            name_span_len[j] = name_span_len[j - 1];
            --j;
        }
        name_start[j] = start;
        name_span_len[j] = length;
    }
    u32 names_cursor = 0;
    for (u32 i = 0; i < count; ++i) {
        if (name_start[i] != names_cursor) {
            print("[files] bundle names not compact\n");
            return;
        }
        names_cursor += name_span_len[i];
    }
    if (names_cursor != names_bytes) {
        print("[files] bundle names unused\n");
        return;
    }
    if (dash_count != 1 || xypm_count > 1 || daily_count > 1) {
        print("[files] bundle member roles rejected\n");
        return;
    }
    // Sort data spans and their names together (count <= 16).
    for (u32 i = 1; i < count; ++i) {
        bundle_entry key = entries[i];
        char key_name[128];
        for (u32 n = 0; n < 128; ++n) { key_name[n] = member_names[i][n]; }
        u32 j = i;
        while (j > 0 && entries[j - 1].data_off > key.data_off) {
            entries[j] = entries[j - 1];
            for (u32 n = 0; n < 128; ++n) { member_names[j][n] = member_names[j - 1][n]; }
            --j;
        }
        entries[j] = key;
        for (u32 n = 0; n < 128; ++n) { member_names[j][n] = key_name[n]; }
    }
    // Contract: overlap, every gap and the tail must be zero and no member may
    // escape its declared bytes. Check before touching the work disk.
    u64 cursor = names_end;
    for (u32 i = 0; i < count; ++i) {
        if (entries[i].data_off < cursor) {
            print("[files] bundle overlap\n");
            return;
        }
        if (!payload_is_zero(cursor, entries[i].data_off - cursor)) {
            print("[files] bundle non-zero padding\n");
            return;
        }
        cursor = entries[i].data_off + entries[i].data_len;
    }
    if (cursor > total || !payload_is_zero(cursor, total - cursor)) {
        print("[files] bundle non-zero padding\n");
        return;
    }
    u32 package_count = 0;
    for (u32 i = 0; i < count; ++i) {
        if (!member_magic_ok(entries[i])) {
            print("[files] bundle magic rejected\n");
            return;
        }
        if (entries[i].type >= 2 && entries[i].type <= 4) { ++package_count; }
    }
    if (package_count > max_staged_packages) {
        print("[files] bundle package count rejected\n");
        return;
    }
    // Verify every member digest before any disk mutation: a bad later member
    // must not leave an earlier member committed.
    for (u32 i = 0; i < count; ++i) {
        if (!member_digest_ok(entries[i])) {
            print("[files] bundle digest mismatch: ");
            if (entries[i].type == 1) {
                print("/usr/bin/dash");
            } else if (entries[i].type == 5) {
                print("/usr/bin/");
                print(member_names[i]);
            } else {
                print("/var/cache/xypm/incoming/");
                print(member_names[i]);
            }
            print("\n");
            return;
        }
    }

    (void)client.mkdir("/var");
    (void)client.mkdir("/var/cache");
    (void)client.mkdir("/var/cache/xypm");
    (void)client.mkdir("/var/cache/xypm/incoming");

    for (u32 i = 0; i < count; ++i) {
        const bundle_entry& e = entries[i];
        const char* name = member_names[i];

        char path[256];
        const char* prefix;
        if (e.type == 1) {
            prefix = "/usr/bin/dash";
            path[0] = 0;
        } else if (e.type == 5) {
            prefix = "/usr/bin/";
            u32 pi = 0;
            while (prefix[pi]) { path[pi] = prefix[pi]; ++pi; }
            for (u32 n = 0; name[n] && pi + 1 < sizeof(path); ++n) { path[pi++] = name[n]; }
            path[pi] = 0;
            prefix = path;
            (void)client.mkdir("/usr");
            (void)client.mkdir("/usr/bin");
        } else {
            prefix = "/var/cache/xypm/incoming/";
            u32 pi = 0;
            while (prefix[pi]) { path[pi] = prefix[pi]; ++pi; }
            for (u32 n = 0; name[n] && pi + 1 < sizeof(path); ++n) { path[pi++] = name[n]; }
            path[pi] = 0;
            prefix = path;
        }
        if (e.type == 1) {
            u32 existing = 0;
            u32 version = 0;
            if (client.stat("/usr/bin/dash", existing, version) != 0) {
                (void)client.mkdir("/usr");
                (void)client.mkdir("/usr/bin");
            }
            if (!install_member_file("/usr/bin/dash", e.data_len, e.sha256, e.data_off)) { return; }
        } else {
            if (!install_member_file(prefix, e.data_len, e.sha256, e.data_off)) { return; }
            // Register only after the member is durably in place: a failed
            // install must not leave a stale path for the supervisor.
            if (e.type >= 2 && e.type <= 4) {
                if (staged_package_count >= max_staged_packages) {
                    print("[files] bundle staging full\n");
                    return;
                }
                char* slot = staged_packages[staged_package_count];
                u32 n = 0;
                while (path[n] && n + 1 < sizeof(staged_packages[0])) { slot[n] = path[n]; ++n; }
                slot[n] = 0;
                ++staged_package_count;
            }
        }
    }
    boot_payload_installed = true;
    print("[files] XOSBND1 bundle processed members=");
    decimal(count);
    print("\n");
}

void install_boot_dash() {
    // Keep the historical name for callers; dispatch to payload installer.
    install_boot_payload();
}

u32 staged_count() { return staged_package_count; }
const char* staged_path(u32 index) {
    if (index >= staged_package_count) { return nullptr; }
    return staged_packages[index];
}
bool bundle_marker_present() {
    // The marker binds the completed install to this exact boot payload, so a
    // later ISO with different packages is not silently skipped.
    u32 existing = 0;
    u32 version = 0;
    if (client.stat(bundle_marker_path, existing, version) != 0 || existing != 65) {
        return false;
    }
    char stored[66]{};
    u32 length = 0;
    if (client.read_all(bundle_marker_path, stored, sizeof(stored), length) != 0 ||
        length != 65 || stored[64] != '\n') {
        return false;
    }
    u8 digest[32];
    char expected[65];
    if (!payload_digest(digest)) { return false; }
    digest_text(digest, expected);
    for (u32 i = 0; i < 64; ++i) { if (stored[i] != expected[i]) { return false; } }
    return true;
}
bool bundle_marker_write() {
    u8 digest[32];
    if (!payload_digest(digest)) { return false; }
    char body[65];
    digest_text(digest, body);
    body[64] = '\n';
    const i64 r = client.replace(bundle_marker_path, body, sizeof(body));
    return r == 0 && client.sync() == 0;
}
bool bundle_install_ok() { return boot_payload_installed; }

void init() {
    if (!client.init()) {
        print("[files] service unavailable\n");
        return;
    }
    install_boot_dash();
    u32 existing = 0;
    u32 version = 0;
    const i64 stat_result = client.stat("hello.elf", existing, version);
    if (stat_result == 0) {
        print("[files] hello.elf present bytes="); decimal(existing); print("\n");
        return;
    }
    if (stat_result != static_cast<i64>(file::status::not_found)) {
        error_line("bootstrap-stat", stat_result);
        return;
    }
    u32 length = 0;
    if (!read_image("hello", image_buffer, sizeof(image_buffer), length)) {
        print("[files] hello image missing\n");
        return;
    }
    const i64 result = client.replace("hello.elf", image_buffer, length);
    if (result != 0) {
        error_line("bootstrap", result);
        return;
    }
    print("[files] ready hello.elf bytes="); decimal(length); print("\n");
}

bool available() {
    return client.ping() == 0;
}

void list(const char* path) {
    file::entry entries[8]{};
    u32 cursor = 0;
    do {
        u32 count = 0;
        const i64 result = client.list(path, entries, 8, count, cursor);
        if (result != 0) { error_line("list", result); return; }
        for (u32 i = 0; i < count; ++i) {
            print(entries[i].name); if (entries[i].directory) { print("/"); }
            print(" size="); decimal(entries[i].size);
            print(" version="); decimal(entries[i].version); print("\n");
        }
    } while (cursor != 0);
}

void make_directory(const char* path) {
    const i64 result = client.mkdir(path);
    if (result != 0) { error_line("mkdir", result); return; }
    print("[files] directory created "); print(path); print("\n");
}

void rename_file(const char* old_path, const char* new_path) {
    const i64 result = client.rename(old_path, new_path);
    if (result != 0) { error_line("rename", result); return; }
    print("[files] renamed "); print(new_path); print("\n");
}

void cat(const char* name) {
    u32 handle = 0, size = 0, version = 0;
    i64 result = client.open(name, file::read_only, handle, size, version);
    if (result != 0) { error_line("cat", result); return; }
    bool any = false;
    u8 last = 0;
    for (;;) {
        result = client.read(handle, image_buffer, 512);
        if (result <= 0) { break; }
        print_bytes(image_buffer, static_cast<u32>(result));
        last = image_buffer[static_cast<u32>(result) - 1];
        any = true;
    }
    const i64 closed = client.close(handle);
    if (result < 0 || closed < 0) { error_line("cat", result < 0 ? result : closed); return; }
    if (any && last != '\n') { print("\n"); }
}

bool exists(const char* name) {
    u32 size = 0, version = 0;
    return client.stat(name, size, version) == 0;
}

void stat(const char* name) {
    u32 size = 0;
    u32 version = 0;
    const i64 result = client.stat(name, size, version);
    if (result != 0) { error_line("stat", result); return; }
    print(name); print(" size="); decimal(size); print(" version="); decimal(version); print("\n");
}

void remove_file(const char* name) {
    const i64 result = client.remove(name);
    if (result != 0) { error_line("remove", result); return; }
    print("[files] removed "); print(name); print("\n");
}

void edit(const char* name) {
    run_editor(name);
}

i64 load(const char* name, u8* buffer, u32 capacity, u32& length) {
    return client.read_all(name, buffer, capacity, length);
}

i64 sync() {
    return client.sync();
}

void filetest() {
    bool ok = true;
    (void)client.remove("t1");
    const char initial[] = "abcde";
    const i64 replaced = client.replace("t1", initial, 5);
    if (replaced != 0) { print("[filetest] failed stage=1a error="); signed_decimal(replaced); print("\n"); return; }
    u32 h1 = 0, h2 = 0, size = 0, version = 0;
    if (client.open("t1", file::read_only, h1, size, version) != 0 || size != 5) {
        print("[filetest] failed stage=1b size="); decimal(size); print("\n"); return;
    }
    if (client.open("t1", file::read_only, h2, size, version) != 0 || size != 5) {
        print("[filetest] failed stage=1c size="); decimal(size); print("\n"); return;
    }
    char a = 0, b = 0, c = 0;
    const i64 first_read = client.read(h1, &a, 1);
    if (first_read != 1 || a != 'a') {
        print("[filetest] failed stage=1d r="); signed_decimal(first_read);
        print(" char="); if (a >= 32 && a <= 126) { char text[2] = {a, 0}; print(text); }
        print(" h="); decimal(h1); print("\n"); return;
    }
    if (client.read(h2, &b, 1) != 1 || b != 'a') { print("[filetest] failed stage=1e\n"); return; }
    if (client.read(h1, &c, 1) != 1 || c != 'b') { print("[filetest] failed stage=1f\n"); return; }
    if (client.seek(h1, 0) != 0) { print("[filetest] failed stage=1g\n"); return; }
    char short_read[10]{};
    if (client.read(h1, short_read, 10) != 5) { print("[filetest] failed stage=1h\n"); return; }
    if (client.read(h1, short_read, 10) != 0) { print("[filetest] failed stage=1i\n"); return; }
    if (client.seek(h1, 99) != 99 || client.read(h1, short_read, 1) != 0) {
        print("[filetest] failed stage=seek_eof\n"); return;
    }
    // Positioning past EOF must not extend the file.
    if (client.fstat(h1, size, version) != 0 || size != 5) {
        print("[filetest] failed stage=seek_size\n"); return;
    }
    if (client.close(h1) != 0 || client.close(h2) != 0) { print("[filetest] failed stage=1j\n"); return; }
    ok = ok && client.open("t1", file::read_write, h1, size, version) == 0;
    ok = ok && client.seek(h1, 5) == 5;
    ok = ok && client.write(h1, "XY", 2) == 2;
    ok = ok && client.close(h1) == 0;
    ok = ok && client.stat("t1", size, version) == 0 && size == 7;
    if (!ok) { print("[filetest] failed stage=2\n"); return; }
    u32 length = 0;
    ok = ok && client.read_all("t1", image_buffer, sizeof(image_buffer), length) == 0 &&
         length == 7 && image_buffer[0] == 'a' && image_buffer[5] == 'X';
    if (!ok) { print("[filetest] failed stage=3\n"); return; }
    // Active readers lock replacement; rejected commit must preserve the file.
    ok = ok && client.open("t1", file::read_only, h1, size, version) == 0;
    ok = ok && client.replace("t1", "bad", 3) < 0;
    ok = ok && client.close(h1) == 0;
    ok = ok && client.stat("t1", size, version) == 0 && size == 7;
    if (!ok) { print("[filetest] failed stage=4\n"); return; }
    char ignored = 0;
    ok = ok && client.read(99, &ignored, 1) < 0;
    ok = ok && client.remove("t1") == 0;
    if (!ok) { print("[filetest] failed stage=6\n"); return; }
    print(ok ? "[filetest] result=pass short=read/eof handles=independent "
               "locked=preserved write=actual invalid=rejected\n"
             : "[filetest] result=FAILED\n");
}
}
