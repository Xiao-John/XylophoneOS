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
        sha256 hash;
        u64 offset = 0;
        u8 got[32];
        while (offset < length) {
            u32 count = static_cast<u32>(length - offset);
            if (count > sizeof(dash_buffer)) { count = sizeof(dash_buffer); }
            if (!read_payload(base + offset, dash_buffer, count)) { return false; }
            hash.update(dash_buffer, count);
            offset += count;
        }
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
    const i64 size = syscall(sys_boot_payload, 0, 0, 0);
    if (size <= 0) { return; }
    if (static_cast<u64>(size) > 32ull * 1024 * 1024) {
        print("[files] boot payload too large\n");
        return;
    }
    if (!boot_payload_is_bundle(static_cast<u64>(size))) {
        // Legacy raw dash ELF path (unchanged behavior).
        u32 existing = 0;
        u32 version = 0;
        if (client.stat("/usr/bin/dash", existing, version) == 0) { return; }
        (void)client.mkdir("/usr");
        (void)client.mkdir("/usr/bin");
        if (!install_member_file("/usr/bin/dash", static_cast<u64>(size), nullptr, 0)) {
            // install_member_file with nullptr sha skips digest check for legacy ELF
            return;
        }
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
    for (u32 i = 0; i < 4; ++i) {
        if (header[28 + i] != 0) { print("[files] bundle reserved\n"); return; }
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
        if (e.reserved != 0 || e.name_len < 1 || e.name_len > 127 ||
            e.name_off + e.name_len > names_bytes ||
            e.data_len < 1 || e.data_off < names_end || e.data_off + e.data_len > total ||
            (e.data_off & 3u) != 0 || e.type < 1 || e.type > 4) {
            print("[files] bundle entry rejected\n");
            return;
        }
        if (e.type == 1) { ++dash_count; }
        if (e.type == 2) { ++xypm_count; }
        if (e.type == 3) { ++daily_count; }
    }
    if (dash_count != 1 || xypm_count > 1 || daily_count > 1) {
        print("[files] bundle member roles rejected\n");
        return;
    }
    // Non-overlap: sort data spans by offset (count <= 16).
    for (u32 i = 1; i < count; ++i) {
        bundle_entry key = entries[i];
        u32 j = i;
        while (j > 0 && entries[j - 1].data_off > key.data_off) {
            entries[j] = entries[j - 1];
            --j;
        }
        entries[j] = key;
    }
    for (u32 i = 1; i < count; ++i) {
        if (entries[i].data_off < entries[i - 1].data_off + entries[i - 1].data_len) {
            print("[files] bundle overlap\n");
            return;
        }
    }

    (void)client.mkdir("/var");
    (void)client.mkdir("/var/cache");
    (void)client.mkdir("/var/cache/xypm");
    (void)client.mkdir("/var/cache/xypm/incoming");

    for (u32 i = 0; i < count; ++i) {
        const bundle_entry& e = entries[i];
        char name[128];
        for (u32 n = 0; n < e.name_len && n + 1 < sizeof(name); ++n) {
            name[n] = static_cast<char>(names_buf[e.name_off + n]);
        }
        name[e.name_len < sizeof(name) ? e.name_len : sizeof(name) - 1] = 0;
        // ASCII / printable / no slash already enforced by generator; double-check slash.
        bool bad = false;
        for (const char* c = name; *c; ++c) {
            if (*c == '/' || static_cast<u8>(*c) < 0x20 || static_cast<u8>(*c) > 0x7e) {
                bad = true;
            }
        }
        if (bad || name[0] == 0) { print("[files] bundle bad name\n"); return; }

        if (e.type == 1) {
            u32 existing = 0;
            u32 version = 0;
            if (client.stat("/usr/bin/dash", existing, version) != 0) {
                (void)client.mkdir("/usr");
                (void)client.mkdir("/usr/bin");
            }
            if (!install_member_file("/usr/bin/dash", e.data_len, e.sha256, e.data_off)) { return; }
        } else {
            char path[256];
            const char* prefix = "/var/cache/xypm/incoming/";
            u32 pi = 0;
            while (prefix[pi]) { path[pi] = prefix[pi]; ++pi; }
            for (u32 n = 0; name[n] && pi + 1 < sizeof(path); ++n) { path[pi++] = name[n]; }
            path[pi] = 0;
            if (!install_member_file(path, e.data_len, e.sha256, e.data_off)) { return; }
        }
    }
    print("[files] XOSBND1 bundle processed members=");
    decimal(count);
    print("\n");
}

void install_boot_dash() {
    // Keep the historical name for callers; dispatch to payload installer.
    install_boot_payload();
}

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
    if (client.seek(h1, 99) != 5 || client.read(h1, short_read, 1) != 0) {
        print("[filetest] failed stage=seek_eof\n"); return;
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
